"""
Preview Service: Generates deterministic storyboard stills (NOT video) for candidate shots.
NEVER calls Veo. Workspace-scoped GCS storage.
Proxy URL: /api/media/previews/{workspace_id}/{campaign_id}/{shot_id}.png
"""
from __future__ import annotations
import asyncio
import io
import os
from PIL import Image, ImageDraw, ImageFont
from app.config import settings


def _font_path(bold: bool = False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    return next((c for c in candidates if os.path.exists(c)), None)


def _pil_font(size: int, bold: bool = False):
    path = _font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _hex_color(value: str, fallback: str = "#111111"):
    v = (value or "").strip()
    if len(v) == 7 and v.startswith("#"):
        try:
            return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))
        except ValueError:
            pass
    fb = fallback.lstrip("#")
    return (int(fb[0:2], 16), int(fb[2:4], 16), int(fb[4:6], 16))


def _wrap_text(text: str, font, max_width: int, max_lines: int = 3) -> list:
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        try:
            w = font.getlength(candidate)
        except AttributeError:
            w = len(candidate) * 8
        if w <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        fin = lines[-1]
        try:
            while fin and font.getlength(f"{fin}...") > max_width:
                fin = fin[:-1]
        except AttributeError:
            pass
        lines[-1] = f"{fin.rstrip()}..."
    return lines


def render_storyboard_fallback(shot, order_label: str, kit, width: int = 720, height: int = 1280) -> bytes:
    """Renders a designed deterministic storyboard preview card as PNG bytes. Never a black card."""
    colors = kit.brand_colors if kit and kit.brand_colors else []
    bg_hex = colors[1] if len(colors) > 1 else "#1A1714"
    fg_hex = colors[0] if len(colors) > 0 else "#F5F5F0"
    accent_hex = colors[2] if len(colors) > 2 else "#FFB347"

    bg = _hex_color(bg_hex, "#1A1714")
    fg = _hex_color(fg_hex, "#F5F5F0")
    accent = _hex_color(accent_hex, "#FFB347")
    surface = tuple(min(255, c + 18) for c in bg)

    canvas = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(canvas)
    margin = 48

    badge_y = 36
    badge_w = 120
    draw.rounded_rectangle((margin, badge_y, margin + badge_w, badge_y + 32), radius=6, fill=accent)
    draw.text((margin + 10, badge_y + 7), order_label, font=_pil_font(13, bold=True), fill="#111111")
    purpose_text = (shot.purpose or "hero").upper()
    draw.rounded_rectangle((margin + badge_w + 12, badge_y, margin + badge_w + 130, badge_y + 32), radius=6, fill=surface)
    draw.text((margin + badge_w + 22, badge_y + 7), purpose_text, font=_pil_font(11), fill=fg)
    dur_text = f"{shot.duration_seconds}s"
    draw.rounded_rectangle((width - margin - 60, badge_y, width - margin, badge_y + 32), radius=6, fill=surface)
    draw.text((width - margin - 48, badge_y + 7), dur_text, font=_pil_font(13, bold=True), fill=accent)

    frame_top = 100
    frame_left = margin + 24
    frame_right = width - margin - 24
    frame_h = int((frame_right - frame_left) * (16 / 9))
    frame_bottom = frame_top + frame_h
    draw.rounded_rectangle((frame_left, frame_top, frame_right, frame_bottom), radius=12, outline=accent, width=2)
    inner_fill = tuple(min(255, c + 30) for c in bg)
    draw.rounded_rectangle((frame_left + 3, frame_top + 3, frame_right - 3, frame_bottom - 3), radius=10, fill=inner_fill)

    csize = 14
    for cx, cy in [(frame_left+10, frame_top+10), (frame_right-10-csize, frame_top+10),
                   (frame_left+10, frame_bottom-10-csize), (frame_right-10-csize, frame_bottom-10-csize)]:
        draw.line([(cx, cy), (cx+csize, cy)], fill=accent, width=2)
        draw.line([(cx, cy), (cx, cy+csize)], fill=accent, width=2)

    cx_mid = (frame_left + frame_right) // 2
    cy_mid = (frame_top + frame_bottom) // 2
    draw.line([(cx_mid-8, cy_mid), (cx_mid+8, cy_mid)], fill=accent, width=1)
    draw.line([(cx_mid, cy_mid-8), (cx_mid, cy_mid+8)], fill=accent, width=1)

    cam_text = (shot.camera or "WIDE SHOT").upper()[:32]
    cam_font = _pil_font(11)
    try:
        cam_bbox = draw.textbbox((0, 0), cam_text, font=cam_font)
        cam_w = cam_bbox[2] - cam_bbox[0]
    except Exception:
        cam_w = len(cam_text) * 7
    draw.text((cx_mid - cam_w//2, cy_mid+16), cam_text, font=cam_font, fill=fg)

    mode_text = (shot.creative_mode or "").replace("_", " ").upper()
    if mode_text and mode_text != "LEGACY":
        draw.text((cx_mid-40, frame_bottom-28), mode_text, font=_pil_font(10), fill=accent)

    info_y = frame_bottom + 20
    for label, value in [("VISUAL", shot.visual or ""), ("ACTION", shot.action or "")]:
        if not value or info_y > height - 120:
            break
        draw.text((margin, info_y), label, font=_pil_font(11, bold=True), fill=accent)
        info_y += 18
        for line in _wrap_text(value, _pil_font(15), width-2*margin, max_lines=2):
            if info_y > height - 100:
                break
            draw.text((margin, info_y), line, font=_pil_font(15), fill=fg)
            info_y += 20
        info_y += 6

    cap_y = height - 96
    draw.line([(margin, cap_y-12), (width-margin, cap_y-12)], fill=surface, width=1)
    for line in _wrap_text(shot.caption or "", _pil_font(13), width-2*margin, max_lines=2):
        draw.text((margin, cap_y), line, font=_pil_font(13), fill=fg)
        cap_y += 17

    audio_short = (shot.audio_direction or "Natural ambience")[:40]
    pill_font = _pil_font(10)
    try:
        pill_w = int(pill_font.getlength(audio_short)) + 20
    except AttributeError:
        pill_w = len(audio_short) * 7 + 20
    draw.rounded_rectangle((margin, height-30, margin+pill_w, height-14), radius=6, fill=surface)
    draw.text((margin+10, height-28), audio_short, font=pill_font, fill=accent)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


class PreviewService:
    def __init__(self):
        self._shot_locks: dict[str, asyncio.Lock] = {}

    def _shot_lock(self, workspace_id: str, campaign_id: str, shot_id: str) -> asyncio.Lock:
        key = f"{workspace_id}:{campaign_id}:{shot_id}"
        lock = self._shot_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._shot_locks[key] = lock
        return lock

    def _proxy_url(self, workspace_id: str, campaign_id: str, shot_id: str) -> str:
        return f"/api/media/previews/{workspace_id}/{campaign_id}/{shot_id}.png"

    def _gcs_blob_name(self, workspace_id: str, campaign_id: str, shot_id: str) -> str:
        return f"preview_stills/{workspace_id}/{campaign_id}/{shot_id}.png"

    def _upload_preview(self, image_bytes: bytes, workspace_id: str, campaign_id: str, shot_id: str) -> str:
        from app.services.ffmpeg_service import ffmpeg_service
        import tempfile, os as _os
        blob_name = self._gcs_blob_name(workspace_id, campaign_id, shot_id)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            ffmpeg_service.bucket.blob(blob_name).upload_from_filename(tmp_path, content_type="image/png")
        finally:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass
        return self._proxy_url(workspace_id, campaign_id, shot_id)

    async def generate_preview(self, shot, campaign, kit, logo_path, product_paths) -> str:
        from app.services.ffmpeg_service import ffmpeg_service
        workspace_id = campaign.workspace_id
        campaign_id = campaign.id
        shot_id = shot.shot_id
        order_label = f"SHOT {shot.order}"

        async with self._shot_lock(workspace_id, campaign_id, shot_id):
            # Re-check storage after acquiring the lock: a concurrent request
            # may already have completed while this coroutine was waiting.
            blob_name = self._gcs_blob_name(workspace_id, campaign_id, shot_id)
            try:
                blob = ffmpeg_service.bucket.blob(blob_name)
                if blob.exists():
                    return self._proxy_url(workspace_id, campaign_id, shot_id)
            except Exception:
                pass

            if settings.demo_mode:
                image_bytes = render_storyboard_fallback(shot, order_label, kit)
            else:
                try:
                    from app.services.image_service import image_service
                    brief = campaign.brief
                    colors_str = ", ".join(kit.brand_colors[:3]) if kit.brand_colors else "dark editorial"
                    prompt = (
                        f"Portrait 9:16 cinematic advertising still. "
                        f"Scene: {shot.visual}. Action: {shot.action}. Camera: {shot.camera}. "
                        f"Color palette: {colors_str}. "
                        f"Subject: {brief.subject_name if brief else ''}. "
                        f"Audience: {brief.audience if brief else ''}. "
                        "Premium editorial advertising photography. "
                        "NO text, NO subtitles, NO logos, NO watermarks, NO readable app UI, "
                        "NO distorted screens, NO distorted hands, NO duplicated people. "
                        "Clean negative space for deterministic overlay composition."
                    )

                    def _gen():
                        from google.genai import types
                        response = image_service.client.models.generate_images(
                            model=image_service.model_name,
                            prompt=prompt,
                            config=types.GenerateImagesConfig(
                                number_of_images=1,
                                aspect_ratio="9:16",
                                output_mime_type="image/png",
                                include_rai_reason=True,
                            ),
                        )
                        if not response.generated_images:
                            raise RuntimeError("No image generated")
                        return response.generated_images[0].image.image_bytes

                    image_bytes_raw = await asyncio.to_thread(_gen)
                    img = Image.open(io.BytesIO(image_bytes_raw)).convert("RGB")
                    img = img.resize((720, 1280), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    image_bytes = buf.getvalue()
                except Exception as e:
                    print(f"WARNING: Imagen preview failed for {shot_id}: {e}. Using storyboard fallback.")
                    image_bytes = render_storyboard_fallback(shot, order_label, kit)

            try:
                return self._upload_preview(image_bytes, workspace_id, campaign_id, shot_id)
            except Exception as e:
                print(f"WARNING: GCS preview upload failed: {e}.")
                return self._proxy_url(workspace_id, campaign_id, shot_id)

    async def generate_previews_for_shots(self, shots, campaign, kit, logo_path, product_paths) -> dict:
        results = {}
        for shot in shots:
            if shot.preview_image_url:
                results[shot.shot_id] = shot.preview_image_url
                continue
            try:
                url = await self.generate_preview(shot, campaign, kit, logo_path, product_paths)
                results[shot.shot_id] = url
            except Exception as e:
                print(f"WARNING: Preview gen failed for {shot.shot_id}: {e}")
        return results

    def render_storyboard_for_shot(self, shot, kit) -> bytes:
        return render_storyboard_fallback(shot, f"SHOT {shot.order}", kit)


preview_service = PreviewService()
