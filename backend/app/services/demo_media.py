from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.campaign import Campaign


class DemoMediaService:
    """Creates original, deterministic media for the public no-key demo."""

    def __init__(self) -> None:
        self.output_dir = Path(__file__).resolve().parents[2] / "data" / "demo_media"

    @staticmethod
    def _font(size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        ]
        path = next((item for item in candidates if os.path.isfile(item)), None)
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()

    @staticmethod
    def _copy(campaign: Campaign, filename: str) -> tuple[str, str, str]:
        subject = campaign.brief.subject_name if campaign.brief else "Demo Brand"
        settings = campaign.production_settings
        headline = (settings.headline if settings else None) or f"Meet {subject}"
        cta = (settings.cta if settings else None) or (campaign.brief.cta if campaign.brief else None) or "Learn more"
        if "carousel_" in filename:
            try:
                index = int(filename.rsplit("_", 1)[-1].split(".", 1)[0])
            except ValueError:
                index = 1
            carousel_copy = {
                1: headline,
                2: f"Built around the needs of {campaign.brief.audience if campaign.brief else 'real people'}.",
                3: campaign.brief.subject_description if campaign.brief else "A clear product story.",
                4: "Evidence-led direction. Brand-safe execution.",
                5: cta,
            }
            headline = carousel_copy.get(index, headline)
        return subject, headline, cta

    def image_bytes(self, campaign: Campaign, filename: str, size: tuple[int, int]) -> bytes:
        width, height = size
        subject, headline, cta = self._copy(campaign, filename)
        canvas = Image.new("RGB", size, "#0B1020")
        draw = ImageDraw.Draw(canvas)
        for y in range(height):
            ratio = y / max(height - 1, 1)
            color = (
                int(11 + 27 * ratio),
                int(16 + 22 * ratio),
                int(32 + 45 * ratio),
            )
            draw.line((0, y, width, y), fill=color)

        accent = "#8B7CFF"
        mint = "#63E6BE"
        margin = max(28, width // 14)
        draw.rounded_rectangle((margin, margin, width - margin, margin + height // 42), radius=8, fill=accent)
        draw.text((margin, margin + height // 18), subject.upper(), font=self._font(max(18, width // 36), True), fill=mint)

        max_chars = max(16, width // 20)
        lines = textwrap.wrap(headline, width=max_chars)[:4]
        title_font = self._font(max(34, width // 15), True)
        line_height = int(getattr(title_font, "size", 42) * 1.18)
        y = int(height * 0.38)
        for line in lines:
            draw.text((margin, y), line, font=title_font, fill="#F7F7FB")
            y += line_height

        draw.rounded_rectangle((margin, int(height * 0.79), width - margin, int(height * 0.88)), radius=max(16, width // 45), fill=accent)
        cta_font = self._font(max(20, width // 30), True)
        cta_text = textwrap.shorten(cta, width=34, placeholder="…")
        box = draw.textbbox((0, 0), cta_text, font=cta_font)
        draw.text(((width - (box[2] - box[0])) / 2, int(height * 0.815)), cta_text, font=cta_font, fill="#090B12")
        draw.text((margin, int(height * 0.93)), "REEL DIRECTOR  •  DEMO OUTPUT", font=self._font(max(11, width // 65), True), fill="#8992A8")

        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()

    def ensure_video(self, campaign: Campaign, filename: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / filename
        if target.is_file() and target.stat().st_size > 0:
            return target

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg is required for demo video rendering")

        first = self.output_dir / f"{target.stem}_01.png"
        second = self.output_dir / f"{target.stem}_02.png"
        first.write_bytes(self.image_bytes(campaign, "post_demo.png", (360, 640)))
        second.write_bytes(self.image_bytes(campaign, "cover_demo.png", (360, 640)))
        command = [
            ffmpeg, "-y",
            "-loop", "1", "-t", "3", "-i", str(first),
            "-loop", "1", "-t", "3", "-i", str(second),
            "-f", "lavfi", "-t", "6", "-i", "anoisesrc=color=pink:amplitude=0.008:sample_rate=48000",
            "-filter_complex",
            "[0:v]fps=24,format=yuv420p[v0];[1:v]fps=24,format=yuv420p[v1];[v0][v1]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-t", "6",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target),
        ]
        subprocess.run(command, check=True, capture_output=True)
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)
        return target


demo_media_service = DemoMediaService()
