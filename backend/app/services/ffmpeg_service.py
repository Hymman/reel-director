import os
import json
import re
import subprocess
import time
import datetime
import tempfile
from google.cloud import storage
from app.config import settings

class FFmpegService:
    def __init__(self):
        self.bucket_name = settings.gcs_bucket_name
        self._storage_client = None
        self._bucket = None

    @property
    def storage_client(self):
        # Keep health/UI startup independent from ADC; media work resolves credentials lazily.
        if self._storage_client is None:
            self._storage_client = storage.Client(project=settings.google_cloud_project)
        return self._storage_client

    @storage_client.setter
    def storage_client(self, value):
        self._storage_client = value

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.storage_client.bucket(self.bucket_name)
        return self._bucket

    @bucket.setter
    def bucket(self, value):
        self._bucket = value

    def download_from_gcs(self, gcs_uri: str, local_path: str):
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")
        
        path_without_gs = gcs_uri[5:]
        bucket_name = path_without_gs.split("/")[0]
        blob_name = "/".join(path_without_gs.split("/")[1:])
        
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
        print(f"Downloaded {gcs_uri} to {local_path}")

    def upload_to_gcs(self, local_path: str, destination_blob_name: str, content_type: str = "video/mp4") -> str:
        """Upload a private object and return the configured delivery URL."""
        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_path, content_type=content_type)

        if settings.media_delivery_mode.lower() == "signed":
            url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )
            return url

        # Local/default delivery stays behind the workspace-scoped Range proxy.
        filename = destination_blob_name.split("/")[-1]
        if destination_blob_name.startswith("final_posts/"):
            media_kind = "posts"
        elif destination_blob_name.startswith("final_covers/"):
            media_kind = "covers"
        else:
            media_kind = "reels"
        return f"/api/media/{media_kind}/{filename}"

    @staticmethod
    def _has_audio(ffprobe_exe: str, path: str) -> bool:
        result = subprocess.run(
            [ffprobe_exe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    @staticmethod
    def _detect_letterbox_crop(ffmpeg_exe: str, ffprobe_exe: str, path: str) -> str:
        """Return a conservative crop filter only for stable baked-in black bars."""
        try:
            probe = subprocess.run(
                [
                    ffprobe_exe,
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "json",
                    path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            source_width = int(stream["width"])
            source_height = int(stream["height"])
            detected = subprocess.run(
                [
                    ffmpeg_exe,
                    "-hide_banner",
                    "-t", "5.8",
                    "-i", path,
                    "-vf", "cropdetect=18:16:0",
                    "-an",
                    "-f", "null",
                    os.devnull,
                ],
                capture_output=True,
                text=True,
            )
            matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", detected.stderr)
            if not matches:
                return ""
            # Stable bars repeat the same crop across the sampled opening shot.
            crop, occurrences = max(
                ((candidate, matches.count(candidate)) for candidate in set(matches)),
                key=lambda item: item[1],
            )
            width, height, x, y = (int(value) for value in crop)
            top_removed = y
            bottom_removed = source_height - (y + height)
            stable = occurrences >= max(3, len(matches) // 2)
            full_width = width >= source_width * 0.90
            meaningful_vertical_bars = source_height * 0.60 <= height <= source_height * 0.94
            balanced = abs(top_removed - bottom_removed) <= max(24, source_height * 0.03)
            if stable and full_width and meaningful_vertical_bars and balanced:
                return f"crop={width}:{height}:{x}:{y},"
        except (KeyError, IndexError, TypeError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
            pass
        return ""

    @staticmethod
    def _font_path(family: str = "Inter", bold: bool = False, italic: bool = False) -> str:
        key = (family or "Inter").strip().casefold()
        if "georgia" in key or "editorial" in key or "serif" in key:
            candidates = [
                r"C:\Windows\Fonts\georgiaz.ttf" if bold and italic else r"C:\Windows\Fonts\georgiab.ttf" if bold else r"C:\Windows\Fonts\georgiai.ttf" if italic else r"C:\Windows\Fonts\georgia.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            ]
        elif "arial" in key:
            candidates = [
                r"C:\Windows\Fonts\arialbi.ttf" if bold and italic else r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\ariali.ttf" if italic else r"C:\Windows\Fonts\arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        else:
            candidates = [
                r"C:\Windows\Fonts\segoeuiz.ttf" if bold and italic else r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeuii.ttf" if italic else r"C:\Windows\Fonts\segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        path = next((item for item in candidates if os.path.exists(item)), None)
        if not path:
            raise RuntimeError("No Turkish-capable production font is installed")
        return path

    def assemble_hybrid_reel(
        self,
        selected_clip: str,
        caption: str,
        card_paths: list[str],
        output_filename: str,
        motion_preset: str = "subtle",
        font_family: str = "Inter",
        caption_preset: str = "clean",
        audio_mode: str = "native_ambient",
        caption_start_seconds: float = 0.0,
    ) -> str:
        """Build a share-ready 1080x1920 reel from one Veo clip and branded cards."""
        import shutil

        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            raise RuntimeError("FFmpeg executable not found in PATH")
        ffprobe_exe = shutil.which("ffprobe") or os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "temp_processing"))
        os.makedirs(base_dir, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="hybrid_", dir=base_dir) as work_dir:
            raw_clip = os.path.join(work_dir, "selected_raw.mp4")
            normalized_clip = os.path.join(work_dir, "selected_captioned.mp4")
            self.download_from_gcs(selected_clip, raw_clip)
            drawtext = self._build_drawtext_filter(
                caption,
                is_cta=False,
                font_family=font_family,
                caption_preset=caption_preset,
                start_seconds=caption_start_seconds,
            )
            has_audio = os.path.isfile(ffprobe_exe) and self._has_audio(ffprobe_exe, raw_clip)
            source_crop = self._detect_letterbox_crop(ffmpeg_exe, ffprobe_exe, raw_clip)
            use_source_audio = has_audio and audio_mode != "silent"
            normalize_cmd = [ffmpeg_exe, "-y", "-i", raw_clip]
            if not use_source_audio:
                audio_source = (
                    "anullsrc=channel_layout=stereo:sample_rate=48000"
                    if audio_mode == "silent"
                    else "anoisesrc=color=pink:amplitude=0.012:sample_rate=48000"
                )
                normalize_cmd.extend(["-f", "lavfi", "-i", audio_source])
            normalize_cmd.extend([
                "-vf", f"{source_crop}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24,{drawtext}",
                "-map", "0:v:0",
                "-map", "0:a:0" if use_source_audio else "1:a:0",
                "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            ])
            # FFmpeg loudnorm cannot analyse an all-zero signal reliably on every
            # platform. Silent mode still carries a valid AAC track, but bypasses
            # loudness analysis; native/ambient modes are normalized for delivery.
            if audio_mode != "silent":
                normalize_cmd.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
            normalize_cmd.extend(["-movflags", "+faststart", "-shortest", normalized_clip])
            subprocess.run(normalize_cmd, check=True)

            rendered_cards = []
            for index, card_path in enumerate(card_paths):
                duration = 1.5
                card_video = os.path.join(work_dir, f"card_{index}.mp4")
                if motion_preset == "none":
                    visual_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24"
                else:
                    zoom_step = "0.0014" if motion_preset == "dynamic" else "0.0007"
                    visual_filter = f"scale=1140:2025,zoompan=z='min(zoom+{zoom_step},1.05)':d={int(duration * 24)}:s=1080x1920:fps=24,fade=t=in:st=0:d=0.2"
                audio_source = (
                    f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration}"
                    if audio_mode == "silent"
                    else f"anoisesrc=color=pink:amplitude=0.012:sample_rate=48000:d={duration}"
                )
                card_cmd = [
                    ffmpeg_exe, "-y", "-loop", "1", "-i", card_path,
                    "-f", "lavfi", "-i", audio_source,
                    "-vf", visual_filter, "-t", str(duration),
                ]
                if audio_mode != "silent":
                    card_cmd.extend(["-af", f"afade=t=in:st=0:d=0.2,afade=t=out:st={duration - 0.35}:d=0.35,loudnorm=I=-30:LRA=7:TP=-6"])
                card_cmd.extend([
                    "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", card_video,
                ])
                subprocess.run(card_cmd, check=True)
                rendered_cards.append(card_video)

            # Start with motion and the hook. Exact product proof and CTA follow.
            sequence = [normalized_clip, *rendered_cards]
            concat_file = os.path.join(work_dir, "concat.txt")
            with open(concat_file, "w", encoding="utf-8") as handle:
                for path in sequence:
                    handle.write(f"file '{path.replace(chr(92), '/')}'\n")
            final_path = os.path.join(work_dir, "hybrid_final.mp4")
            final_cmd = [
                ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            ]
            if audio_mode != "silent":
                final_cmd.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
            final_cmd.extend(["-movflags", "+faststart", final_path])
            subprocess.run(final_cmd, check=True)
            return self.upload_to_gcs(final_path, f"final_reels/{int(time.time())}_{output_filename}")

    def assemble_slideshow_reel(
        self,
        card_paths: list[str],
        output_filename: str,
        motion_preset: str = "subtle",
        audio_mode: str = "native_ambient",
    ) -> str:
        """Turn ordered 9:16 or 4:5 campaign cards into an automatic 9:16 Reel.

        This is the zero-Veo motion format: deterministic brand cards, controlled
        pan/zoom, short transitions and a valid AAC track. The same source cards
        can also be delivered separately as a manually swiped carousel.
        """
        import shutil

        if not 2 <= len(card_paths) <= 8:
            raise ValueError("Slideshow Reel requires between 2 and 8 ordered cards")
        if any(not os.path.isfile(path) for path in card_paths):
            raise FileNotFoundError("One or more slideshow cards do not exist")

        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            raise RuntimeError("FFmpeg executable not found in PATH")
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "temp_processing"))
        os.makedirs(base_dir, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="slideshow_", dir=base_dir) as work_dir:
            rendered_cards: list[str] = []
            for index, card_path in enumerate(card_paths):
                duration = 2.0 if index == len(card_paths) - 1 else 1.65
                frame_count = int(duration * 24)
                rendered = os.path.join(work_dir, f"slide_{index:02d}.mp4")
                if motion_preset == "none":
                    visual_filter = (
                        "scale=1080:1920:force_original_aspect_ratio=decrease,"
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#0B1324,fps=24,"
                        f"fade=t=in:st=0:d=0.18,fade=t=out:st={duration - 0.22}:d=0.22"
                    )
                else:
                    zoom_step = "0.0015" if motion_preset == "dynamic" else "0.0007"
                    visual_filter = (
                        "scale=1080:1920:force_original_aspect_ratio=decrease,"
                        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#0B1324,"
                        f"zoompan=z='min(zoom+{zoom_step},1.05)':d={frame_count}:s=1080x1920:fps=24,"
                        f"fade=t=in:st=0:d=0.18,fade=t=out:st={duration - 0.22}:d=0.22"
                    )
                audio_source = (
                    f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration}"
                    if audio_mode == "silent"
                    else f"anoisesrc=color=pink:amplitude=0.010:sample_rate=48000:d={duration}"
                )
                command = [
                    ffmpeg_exe,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    card_path,
                    "-f",
                    "lavfi",
                    "-i",
                    audio_source,
                    "-vf",
                    visual_filter,
                    "-t",
                    str(duration),
                ]
                if audio_mode != "silent":
                    command.extend([
                        "-af",
                        f"afade=t=in:st=0:d=0.18,afade=t=out:st={duration - 0.28}:d=0.28,loudnorm=I=-30:LRA=7:TP=-6",
                    ])
                command.extend([
                    "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", rendered,
                ])
                subprocess.run(command, check=True)
                rendered_cards.append(rendered)

            concat_file = os.path.join(work_dir, "concat.txt")
            with open(concat_file, "w", encoding="utf-8") as handle:
                for path in rendered_cards:
                    handle.write(f"file '{path.replace(chr(92), '/')}'\n")
            final_path = os.path.join(work_dir, "slideshow_final.mp4")
            final_command = [
                ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
                "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            ]
            if audio_mode != "silent":
                final_command.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
            final_command.extend(["-movflags", "+faststart", final_path])
            subprocess.run(final_command, check=True)
            return self.upload_to_gcs(final_path, f"final_reels/{int(time.time())}_{output_filename}")

    def _build_drawtext_filter(
        self,
        text: str,
        is_cta: bool = False,
        font_family: str = "Inter",
        caption_preset: str = "clean",
        start_seconds: float = 0.0,
    ) -> str:
        from PIL import ImageFont

        editorial = caption_preset == "editorial"
        font_path = self._font_path(font_family, bold=caption_preset == "bold" or is_cta, italic=editorial)
        font_path_ff = font_path.replace("\\", "/").replace(":", "\\:") # FFmpeg friendly path
        max_width = 900
        max_lines = 3
        
        start_size = 88 if is_cta else 76 if caption_preset == "bold" else 66 if caption_preset == "clean" else 60
        min_size = 34
        
        best_lines = []
        best_size = start_size
        
        for font_size in range(start_size, min_size - 1, -2):
            font = ImageFont.truetype(font_path, font_size)
            words = text.split()
            
            # If a single word is wider than max_width, we must shrink font
            if any(font.getlength(w) > max_width for w in words):
                continue
                
            lines = []
            if words:
                current_line = words[0]
                for word in words[1:]:
                    test_line = current_line + " " + word
                    if font.getlength(test_line) <= max_width:
                        current_line = test_line
                    else:
                        lines.append(current_line)
                        current_line = word
                lines.append(current_line)
                
            if len(lines) <= max_lines:
                best_lines = lines
                best_size = font_size
                break
        else:
            raise ValueError(f"Text cannot fit in 3 lines within 900px safe-area even at font size {min_size}. Text: '{text}'")

        if is_cta:
            base_y = "(h)/2"
        else:
            base_y = "h-(h/4)"
            
        filters = []
        line_height = best_size * 1.3
        start_offset = - ((len(best_lines) - 1) * line_height) / 2
        
        for i, line in enumerate(best_lines):
            safe_line = line.replace("'", "").replace(":", "\\:")
            y_expr = f"{base_y}+{start_offset + i*line_height}"
            if caption_preset == "bold" and not is_cta:
                style = f"fontfile='{font_path_ff}':fontcolor=white:fontsize={best_size}:box=1:boxcolor=black@0.72:boxborderw=18:borderw=0:fix_bounds=1"
            elif caption_preset == "editorial" and not is_cta:
                style = f"fontfile='{font_path_ff}':fontcolor=white:fontsize={best_size}:borderw=2:bordercolor=black@0.85:shadowx=1:shadowy=2:shadowcolor=black@0.8:fix_bounds=1"
            else:
                style = f"fontfile='{font_path_ff}':fontcolor=white:fontsize={best_size}:borderw=4:bordercolor=black@0.9:shadowx=2:shadowy=2:shadowcolor=black@0.7:fix_bounds=1"
            enable = f":enable='gte(t\\,{start_seconds:.3f})'" if start_seconds > 0 else ""
            filters.append(f"drawtext=text='{safe_line}':{style}:x=(w-text_w)/2:y={y_expr}{enable}")
            
        return ",".join(filters)

    def assemble_reel(
        self,
        clips: list[str],
        texts: list[str],
        output_filename: str,
        cta_text: str = None,
        font_family: str = "Inter",
        caption_preset: str = "clean",
        audio_mode: str = "native_ambient",
    ) -> str:
        """
        Assembles a final reel from local clip paths and text overlays.
        Returns the HTTPS URL of the final uploaded video.
        """
        import shutil
        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            raise RuntimeError("FFmpeg executable not found in PATH. Please install FFmpeg.")
        ffprobe_exe = shutil.which("ffprobe") or os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
            
        work_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "temp_processing")
        os.makedirs(work_dir, exist_ok=True)
        
        local_files = []
        for i, clip_uri in enumerate(clips):
            ext = clip_uri.split('.')[-1]
            if not ext or '?' in ext: ext = 'mp4'
            local_path = os.path.join(work_dir, f"clip_{i}_raw.{ext}")
            self.download_from_gcs(clip_uri, local_path)
            
            # Burn text and normalize to share-ready 1080x1920 social format.
            text_burned_path = os.path.join(work_dir, f"clip_{i}_text.{ext}")
            
            # Use scale and fps filters before drawtext for robust normalization
            multi_drawtext = self._build_drawtext_filter(texts[i], is_cta=False, font_family=font_family, caption_preset=caption_preset)
            filter_str = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24,{multi_drawtext}"

            has_audio = os.path.isfile(ffprobe_exe) and self._has_audio(ffprobe_exe, local_path)
            use_source_audio = has_audio and audio_mode != "silent"
            cmd_text = [ffmpeg_exe, "-y", "-i", local_path]
            if not use_source_audio:
                fallback_audio = (
                    "anullsrc=channel_layout=stereo:sample_rate=48000"
                    if audio_mode == "silent"
                    else "anoisesrc=color=pink:amplitude=0.012:sample_rate=48000"
                )
                cmd_text.extend(["-f", "lavfi", "-i", fallback_audio])
            cmd_text.extend([
                "-vf", filter_str,
                "-map", "0:v:0",
                "-map", "0:a:0" if use_source_audio else "1:a:0",
                "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            ])
            if audio_mode != "silent":
                cmd_text.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
            cmd_text.extend(["-shortest", text_burned_path])
            print("Running text overlay and normalization for clip:", " ".join(cmd_text))
            subprocess.run(cmd_text, check=True)
            
            local_files.append(text_burned_path)

        if cta_text:
            end_card_path = os.path.join(work_dir, "end_card.mp4")
            multi_drawtext_cta = self._build_drawtext_filter(cta_text, is_cta=True, font_family=font_family, caption_preset=caption_preset)
            # Create a 3-second CTA card matching normalized format exactly.
            cmd_end_card = [
                ffmpeg_exe, "-y", 
                "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=24:d=3",
                "-f", "lavfi", "-i", (
                    "anullsrc=channel_layout=stereo:sample_rate=48000:d=3"
                    if audio_mode == "silent"
                    else "anoisesrc=color=pink:amplitude=0.012:sample_rate=48000:d=3"
                ),
                "-vf", multi_drawtext_cta,
            ]
            if audio_mode != "silent":
                cmd_end_card.extend(["-af", "afade=t=in:st=0:d=0.2,afade=t=out:st=2.65:d=0.35,loudnorm=I=-30:LRA=7:TP=-6"])
            cmd_end_card.extend([
                "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest",
                end_card_path
            ])
            print("Generating CTA end card:", " ".join(cmd_end_card))
            subprocess.run(cmd_end_card, check=True)
            local_files.append(end_card_path)
            
        # Write concat demuxer file
        list_file = os.path.join(work_dir, "concat.txt")
        with open(list_file, "w") as f:
            for lf in local_files:
                safe_path = lf.replace('\\', '/')
                f.write(f"file '{safe_path}'\n")

        # Concat and finalize with a social-safe codec/audio contract.
        concat_mp4 = os.path.join(work_dir, "concat.mp4")
        cmd_concat = [
            ffmpeg_exe, "-y", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            concat_mp4
        ]
        
        print("Running concat:", " ".join(cmd_concat))
        subprocess.run(cmd_concat, check=True)

        final_mp4 = os.path.join(work_dir, "final.mp4")
        final_cmd = [
            ffmpeg_exe, "-y", "-i", concat_mp4,
            "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        ]
        if audio_mode != "silent":
            final_cmd.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
        final_cmd.extend(["-movflags", "+faststart", final_mp4])
        subprocess.run(final_cmd, check=True)
        
        # Upload
        dest_blob = f"final_reels/{int(time.time())}_{output_filename}"
        signed_url = self.upload_to_gcs(final_mp4, dest_blob)
        
        # Cleanup
        for lf in local_files:
            try: os.remove(lf)
            except: pass
        try: os.remove(list_file)
        except: pass
        try: os.remove(final_mp4)
        except: pass
        try: os.remove(concat_mp4)
        except: pass
        
        return signed_url

ffmpeg_service = FFmpegService()
