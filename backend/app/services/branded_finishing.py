import io
import os
import re
import tempfile
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

from app.models.campaign import Campaign, ProductionSettings
from app.models.library import BrandKit
from app.services.ffmpeg_service import ffmpeg_service


def _font_candidates(family: str, bold: bool = False, italic: bool = False) -> list[str]:
    key = (family or "Inter").strip().casefold()
    if "georgia" in key or "editorial" in key or "serif" in key:
        windows = r"C:\Windows\Fonts\georgiaz.ttf" if bold and italic else r"C:\Windows\Fonts\georgiab.ttf" if bold else r"C:\Windows\Fonts\georgiai.ttf" if italic else r"C:\Windows\Fonts\georgia.ttf"
        linux = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    elif "arial" in key:
        windows = r"C:\Windows\Fonts\arialbi.ttf" if bold and italic else r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\ariali.ttf" if italic else r"C:\Windows\Fonts\arial.ttf"
        linux = "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    else:
        windows = r"C:\Windows\Fonts\segoeuiz.ttf" if bold and italic else r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeuii.ttf" if italic else r"C:\Windows\Fonts\segoeui.ttf"
        linux = "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf" if bold and italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return [windows, linux]


def resolve_font_path(family: str = "Inter", bold: bool = False, italic: bool = False) -> str | None:
    return next((candidate for candidate in _font_candidates(family, bold, italic) if os.path.exists(candidate)), None)


def _font(size: int, bold: bool = False, family: str = "Inter", italic: bool = False):
    path = resolve_font_path(family, bold=bold, italic=italic)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _hex(value: str, fallback: str) -> str:
    value = (value or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            pass
    return fallback


def _mix_hex(base: str, overlay: str, ratio: float) -> str:
    """Return a solid RGB blend so Pillow's final RGB export keeps contrast."""
    ratio = max(0.0, min(1.0, ratio))
    try:
        base_rgb = tuple(int(base[index:index + 2], 16) for index in (1, 3, 5))
        overlay_rgb = tuple(int(overlay[index:index + 2], 16) for index in (1, 3, 5))
    except (TypeError, ValueError):
        return base
    mixed = tuple(round(base_value * (1 - ratio) + overlay_value * ratio) for base_value, overlay_value in zip(base_rgb, overlay_rgb))
    return "#" + "".join(f"{value:02X}" for value in mixed)


def _palette_for(campaign: Campaign, kit: BrandKit) -> tuple[str, str, str]:
    """Resolve a deterministic three-color treatment from the saved Brand Kit."""
    colors = kit.brand_colors or ["#F5F5F0", "#141210", "#FFB347"]
    foreground = _hex(colors[0], "#F5F5F0")
    background = _hex(colors[1] if len(colors) > 1 else "#141210", "#141210")
    accent = _hex(colors[2] if len(colors) > 2 else colors[0], "#FFB347")
    treatment = getattr(campaign.production_settings, "visual_treatment", "brand_safe") if campaign.production_settings else "brand_safe"
    if treatment == "campaign_mood":
        return (
            _mix_hex(foreground, "#FFFFFF", 0.10),
            _mix_hex(background, accent, 0.18),
            _mix_hex(accent, foreground, 0.12),
        )
    if treatment == "high_contrast":
        return ("#FFFFFF", _mix_hex("#05070B", background, 0.16), accent)
    return foreground, background, accent


def _rgb(value: str, fallback: tuple[int, int, int] = (12, 10, 8)) -> tuple[int, int, int]:
    try:
        return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))
    except (TypeError, ValueError):
        return fallback


def _shorten_copy(text: str | None, max_chars: int) -> str:
    """Keep approved copy readable without exposing long planning-language fragments."""
    value = " ".join((text or "").split()).strip()
    if len(value) <= max_chars:
        return value

    window = value[: max_chars + 1]
    for punctuation in (".", "!", "?", ";", ":"):
        boundary = window.rfind(punctuation)
        if boundary >= int(max_chars * 0.45):
            shortened = window[: boundary + 1].rstrip(";,: ")
            return shortened if shortened.endswith((".", "!", "?")) else f"{shortened}."

    boundary = window.rfind(" ")
    if boundary < int(max_chars * 0.45):
        boundary = max_chars
    return f"{window[:boundary].rstrip(' ,;:-')}…"


_PLANNING_LANGUAGE_PATTERNS = (
    r"\bkampanyanın anlatacağı\b",
    r"\bkampanya anlatısı\b",
    r"\bkampanya dili\b",
    r"\byaratıcı hipotez\b",
    r"\bkreatif yön(?:elim)?\b",
    r"\büretim ekibi\b",
    r"\bdahili\b",
    r"\bplanlama dili\b",
    r"\bthe campaign(?:'s| carries| will| should)?\b",
    r"\bcampaign narrative\b",
    r"\bcreative direction\b",
    r"\bcreative hypothesis\b",
    r"\bevidence used\b",
    r"\bresearch suggests\b",
    r"\binternal (?:copy|note|language|field)\b",
    r"\bthe struggle to\b",
    r"\bthe unfulfilled desire to\b",
    r"\bcombined with\b",
    r"\bhindered by\b",
)

_PRODUCTION_LANGUAGE_PATTERNS = (
    r"\b(?:shot|scene|camera|visual treatment|output language)\b",
    r"\b(?:customer-facing|deterministic|generated|production)\b",
    r"\b(?:synchronized|native ambience|room tone|sound effects?)\b",
    r"\b(?:dialogue|narration|lyrics)\b",
    r"\b(?:exact|supplied|uploaded).{0,45}\b(?:logo|screenshot|asset|screen)\b",
    r"\b(?:readable|fabricated|bright blank).{0,35}\b(?:ui|text|screen|interface)\b",
    r"\b(?:realistic )?adult waking\b",
)

_ASSET_INVENTORY_PATTERNS = (
    r"\b(?:mobil|mobile)?\s*(?:uygulama|app)\s*(?:ekranı|screen|screenshot)\b",
    r"\b(?:uygulama|app)\s*(?:simgesi|icon)\b",
    r"\b(?:monogram|logo(?:su)?)\b",
    r"^(?:üst|alt)\s+gezinme çubuğu\b",
    r"^(?:top|bottom)\s+navigation bar\b",
    r"^(?:içerik bölümleri|content sections|etiketler|labels|yıldız simgeleri|star icons)\b",
    r"\b(?:koyu mod kullanıcı arayüzü|dark mode user interface)\b",
    r"\b(?:lacivert|indigo).*(?:arka plan(?:lar(?:ı)?)?|backgrounds?)\b",
    r"\b(?:yuvarlak köşeli|rounded corner).*(?:kart(?:lar)?|cards?|düğme(?:ler)?|buttons?)\b",
    r"\b(?:arka plan(?:lar(?:ı)?)?|backgrounds?|kart(?:lar)?|cards?|düğme(?:ler)?|buttons?)\b",
)


def _contains_planning_language(text: str | None) -> bool:
    """Reject production notes before they reach customer-facing creative."""
    value = " ".join((text or "").split()).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _PLANNING_LANGUAGE_PATTERNS)


def _contains_asset_inventory_language(text: str | None) -> bool:
    """Keep uploaded-file/UI inventory labels out of customer benefit cards."""
    value = " ".join((text or "").split()).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _ASSET_INVENTORY_PATTERNS)


def _contains_production_language(text: str | None) -> bool:
    value = " ".join((text or "").split()).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _PRODUCTION_LANGUAGE_PATTERNS)


def _requirement_customer_copy(text: str | None, max_chars: int = 82) -> str:
    """Keep only a benefit/detail from a brief requirement, never its production wrapper."""
    value = " ".join((text or "").split()).strip()
    if not value:
        return ""
    if ":" in value and re.search(r"\b(?:ritual|details?|steps?)\b", value.split(":", 1)[0], re.IGNORECASE):
        value = value.split(":", 1)[1].strip()
    if (
        _contains_planning_language(value)
        or _contains_asset_inventory_language(value)
        or _contains_production_language(value)
    ):
        return ""
    if value and value[0].islower():
        value = value[0].upper() + value[1:]
    return _shorten_copy(value, max_chars)


def _copy_is_similar(left: str, right: str) -> bool:
    left_words = set(re.findall(r"[\w']+", left.casefold()))
    right_words = set(re.findall(r"[\w']+", right.casefold()))
    if not left_words or not right_words:
        return False
    return len(left_words & right_words) / min(len(left_words), len(right_words)) >= 0.72


def _customer_facing_copy(text: str | None, fallback: str, max_chars: int) -> str:
    """Return concise approved copy, replacing internal planning language with a safe fallback."""
    candidate = _shorten_copy(text, max_chars)
    if (
        not candidate
        or _contains_planning_language(candidate)
        or _contains_asset_inventory_language(candidate)
        or _contains_production_language(candidate)
    ):
        candidate = _shorten_copy(fallback, max_chars)
    return candidate


def _safe_generated_background(background_bytes: bytes, size: tuple[int, int]) -> Image.Image:
    """Turn provider art into a non-literal mood layer so invented text/UI cannot survive.

    Image models may occasionally ignore a no-text instruction and render an ad,
    badge, screen or claim. Strong downsampling plus blur preserves palette and
    atmosphere while deterministically destroying readable glyphs and fake UI.
    Exact logo, product proof and copy are then added by our own renderer.
    """
    source = Image.open(io.BytesIO(background_bytes)).convert("RGB")
    fitted = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    sample_size = (max(24, size[0] // 18), max(30, size[1] // 18))
    mood = fitted.resize(sample_size, Image.Resampling.LANCZOS)
    mood = mood.filter(ImageFilter.GaussianBlur(radius=3.5))
    mood = mood.resize(size, Image.Resampling.BICUBIC)
    mood = mood.filter(ImageFilter.GaussianBlur(radius=8))
    return mood.convert("RGBA")


def _wrap_pixels(text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        final = lines[-1]
        while final and font.getlength(f"{final}…") > max_width:
            final = final[:-1]
        lines[-1] = f"{final.rstrip()}…"
    return lines


def _fit_headline(text: str, family: str, max_width: int, max_lines: int, start_size: int, min_size: int = 32, bold: bool = True, italic: bool = False) -> tuple[list[str], ImageFont.ImageFont]:
    for size in range(start_size, min_size - 1, -2):
        f = _font(size, bold=bold, family=family, italic=italic)
        lines = _wrap_pixels(text, f, max_width, max_lines + 1)
        if len(lines) <= max_lines:
            return lines, f
    fallback_font = _font(min_size, bold=bold, family=family, italic=italic)
    return _wrap_pixels(text, fallback_font, max_width, max_lines), fallback_font


class BrandedFinishingService:
    @staticmethod
    def _trim_outer_whitespace(image: Image.Image, tolerance: int = 16) -> Image.Image:
        """Remove transparent and near-white padding around uploaded product captures.

        Store screenshots and exported mockups often arrive on a larger white
        canvas. Preserving that canvas creates an obvious white strip inside the
        deterministic device frame. Only padding connected to the outer image
        bounds is removed; internal white UI regions remain intact.
        """
        rgba = image.convert("RGBA")
        alpha_bbox = rgba.getchannel("A").getbbox()
        if alpha_bbox:
            rgba = rgba.crop(alpha_bbox)

        rgb = rgba.convert("RGB")
        pixels = rgb.load()
        width, height = rgb.size

        def row_is_white(y: int) -> bool:
            return all(
                pixels[x, y][0] >= 255 - tolerance
                and pixels[x, y][1] >= 255 - tolerance
                and pixels[x, y][2] >= 255 - tolerance
                for x in range(width)
            )

        def column_is_white(x: int, top: int, bottom: int) -> bool:
            return all(
                pixels[x, y][0] >= 255 - tolerance
                and pixels[x, y][1] >= 255 - tolerance
                and pixels[x, y][2] >= 255 - tolerance
                for y in range(top, bottom + 1)
            )

        top = 0
        while top < height - 1 and row_is_white(top):
            top += 1
        bottom = height - 1
        while bottom > top and row_is_white(bottom):
            bottom -= 1
        left = 0
        while left < width - 1 and column_is_white(left, top, bottom):
            left += 1
        right = width - 1
        while right > left and column_is_white(right, top, bottom):
            right -= 1

        # Avoid treating a legitimately almost-white creative as empty.
        if (right - left + 1) * (bottom - top + 1) < width * height * 0.08:
            return rgba
        return rgba.crop((left, top, right + 1, bottom + 1))

    @staticmethod
    def _paste_contained(
        canvas: Image.Image,
        asset_path: str | None,
        box: tuple[int, int, int, int],
        radius: int = 20,
        trim_outer_whitespace: bool = False,
    ) -> bool:
        if not asset_path or not os.path.isfile(asset_path):
            return False
        try:
            image = Image.open(asset_path).convert("RGBA")
            if trim_outer_whitespace:
                image = BrandedFinishingService._trim_outer_whitespace(image)
            target_w = box[2] - box[0]
            target_h = box[3] - box[1]
            image.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            x = box[0] + (target_w - image.width) // 2
            y = box[1] + (target_h - image.height) // 2
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
            canvas.paste(image, (x, y), mask)
            return True
        except Exception:
            return False

    def _draw_brand_lockup(
        self,
        canvas: Image.Image,
        kit: BrandKit,
        logo_path: str | None,
        foreground: str,
        accent: str,
        width: int = 720,
        top_y: int | None = None,
    ):
        draw = ImageDraw.Draw(canvas)
        margin = 48 if width == 720 else 64
        top_y = top_y if top_y is not None else (48 if width == 720 else 64)
        
        # Subtle top accent bar
        draw.rounded_rectangle((margin, top_y, width - margin, top_y + 4), radius=2, fill=accent)
        
        logo_rendered = False
        logo_w = 48 if width == 720 else 64
        logo_h = 48 if width == 720 else 64
        logo_y = top_y + 16
        
        if logo_path and os.path.isfile(logo_path):
            logo_box = (margin, logo_y, margin + logo_w, logo_y + logo_h)
            logo_rendered = self._paste_contained(canvas, logo_path, logo_box, radius=10)

        brand_text_x = margin + logo_w + 14 if logo_rendered else margin
        brand_text_y = logo_y + (10 if width == 720 else 14)
        brand_name = (kit.brand_name or "REEL DIRECTOR").upper()
        draw.text(
            (brand_text_x, brand_text_y),
            brand_name,
            font=_font(18 if width == 720 else 24, True, kit.font_family),
            fill=foreground,
        )

    def _draw_device_mockup(
        self,
        canvas: Image.Image,
        product_path: Optional[str],
        box: tuple[int, int, int, int],
        accent: str,
        subject_name: str,
        font_family: str
    ):
        """Draw a clean, modern device mockup frame with subtle shadow and screen insert."""
        draw = ImageDraw.Draw(canvas)
        bx0, by0, bx1, by1 = box
        frame_w = bx1 - bx0
        frame_h = by1 - by0

        # 1. Subtle drop shadow
        shadow_box = (bx0 + 6, by0 + 8, bx1 + 6, by1 + 8)
        draw.rounded_rectangle(shadow_box, radius=28, fill="#080808")

        # 2. Outer phone/device chassis
        draw.rounded_rectangle(box, radius=26, fill="#242220", outline="#3E3A36", width=2)

        # 3. Inner screen area
        screen_box = (bx0 + 10, by0 + 12, bx1 - 10, by1 - 12)
        draw.rounded_rectangle(screen_box, radius=18, fill="#12100E")

        # 4. Top speaker/notch bar
        notch_w = int(frame_w * 0.28)
        notch_x0 = bx0 + (frame_w - notch_w) // 2
        draw.rounded_rectangle((notch_x0, by0 + 16, notch_x0 + notch_w, by0 + 22), radius=3, fill="#242220")

        # 5. Paste product asset inside screen or render styled product badge
        content_box = (screen_box[0] + 4, screen_box[1] + 16, screen_box[2] - 4, screen_box[3] - 16)
        pasted = self._paste_contained(
            canvas,
            product_path,
            content_box,
            radius=14,
            trim_outer_whitespace=True,
        )
        if not pasted:
            # Styled app card fallback
            inner_draw = ImageDraw.Draw(canvas)
            card_w = content_box[2] - content_box[0]
            card_h = content_box[3] - content_box[1]
            cx = content_box[0] + card_w // 2
            cy = content_box[1] + card_h // 2
            
            # App icon box
            icon_box = (cx - 42, cy - 65, cx + 42, cy + 19)
            inner_draw.rounded_rectangle(icon_box, radius=16, fill=accent)
            inner_draw.text((cx - 16, cy - 50), "📱", font=_font(32, True, font_family), fill="#111111")
            
            # App title
            t_box = inner_draw.textbbox((0, 0), subject_name, font=_font(22, True, font_family))
            inner_draw.text((cx - (t_box[2] - t_box[0]) / 2, cy + 32), subject_name, font=_font(22, True, font_family), fill="#FFFFFF")

    @staticmethod
    def _campaign_copy(campaign: Campaign) -> ProductionSettings:
        if campaign.production_settings:
            return campaign.production_settings
        headline = campaign.brief.subject_name if campaign.brief else "A better way"
        cta = (campaign.brief.cta if campaign.brief else None) or "Learn more"
        caption = campaign.brief.subject_description if campaign.brief else ""
        return ProductionSettings(headline=headline, cta=cta, caption=caption)

    def render_vertical_cards(
        self,
        campaign: Campaign,
        kit: BrandKit,
        logo_path: str | None,
        product_paths: list[str],
        output_dir: str,
    ) -> list[str]:
        """Render professional product-proof and CTA cards following the hero clip."""
        foreground, background, accent = _palette_for(campaign, kit)
        settings = self._campaign_copy(campaign)
        subject_name = campaign.brief.subject_name if campaign.brief else (kit.brand_name or "Your product")
        cards = []

        # ==========================================
        # CARD 1: Product Proof Showcase (9:16)
        # ==========================================
        product_card = Image.new("RGBA", (720, 1280), background)
        draw = ImageDraw.Draw(product_card)
        self._draw_brand_lockup(product_card, kit, logo_path, foreground, accent, width=720)

        # Device mockup frame in center
        device_box = (175, 140, 545, 750)
        self._draw_device_mockup(
            product_card,
            product_paths[0] if product_paths else None,
            device_box,
            accent,
            subject_name,
            kit.font_family,
        )

        # Category / Eyebrow pill
        eyebrow_text = "UYGULAMA ÖNİZLEMESİ" if getattr(campaign.brief, 'output_language', 'en') == 'tr' else "PRODUCT SHOWCASE"
        draw.rounded_rectangle((48, 785, 230, 812), radius=6, fill="#221E1A")
        draw.text((58, 791), eyebrow_text, font=_font(11, True, kit.font_family), fill=accent)

        # Headline below device
        headline_lines, headline_font = _fit_headline(
            settings.headline,
            kit.font_family,
            max_width=624,
            max_lines=2,
            start_size=42,
            min_size=30,
            bold=kit.caption_preset != "editorial",
            italic=kit.caption_preset == "editorial"
        )
        y = 830
        for line in headline_lines:
            draw.text((48, y), line, font=headline_font, fill=foreground)
            y += int(headline_font.size * 1.22)

        # Supporting Caption (if distinct from headline and space permits)
        supporting = settings.caption.strip() if settings.caption else ""
        if supporting and supporting != settings.headline and y < 1030:
            caption_font = _font(22, False, kit.font_family)
            for line in _wrap_pixels(supporting, caption_font, 624, 2):
                draw.text((48, y + 8), line, font=caption_font, fill="#A8A29E")
                y += 30

        # Safe zone spacer at bottom (keeps y < 1160)
        draw.line([(48, 1140), (672, 1140)], fill="#242220", width=1)
        product_path = os.path.join(output_dir, "brand_product_proof.png")
        product_card.convert("RGB").save(product_path, "PNG")
        cards.append(product_path)

        # ==========================================
        # CARD 2: CTA Payoff End Card (9:16)
        # ==========================================
        cta_card = Image.new("RGBA", (720, 1280), background)
        draw = ImageDraw.Draw(cta_card)
        self._draw_brand_lockup(cta_card, kit, logo_path, foreground, accent, width=720)

        # Headline / Value proposition recap
        draw.text((48, 320), subject_name.upper(), font=_font(14, True, kit.font_family), fill=accent)
        cta_headline_lines, cta_h_font = _fit_headline(
            settings.headline,
            kit.font_family,
            max_width=624,
            max_lines=3,
            start_size=48,
            min_size=32,
            bold=True
        )
        y = 355
        for line in cta_headline_lines:
            draw.text((48, y), line, font=cta_h_font, fill=foreground)
            y += int(cta_h_font.size * 1.22)

        # Subtitle reassurance
        sub_text = "Hemen indirin ve ücretsiz deneyin." if getattr(campaign.brief, 'output_language', 'en') == 'tr' else "Download today and start free."
        draw.text((48, y + 10), sub_text, font=_font(22, False, kit.font_family), fill="#A8A29E")

        # Balanced CTA Button / Card
        btn_y = y + 75
        cta_font = _font(34, True, kit.font_family)
        cta_lines = _wrap_pixels(settings.cta, cta_font, 520, 2)
        btn_height = 80 if len(cta_lines) <= 1 else 115

        if kit.cta_treatment == "card":
            draw.rounded_rectangle((48, btn_y, 672, btn_y + btn_height), radius=20, fill=accent)
            for idx, cl in enumerate(cta_lines):
                draw.text((76, btn_y + 20 + idx * 40), cl, font=cta_font, fill="#111111")
            draw.text((615, btn_y + 22), "↗", font=_font(30, True, kit.font_family), fill="#111111")
        elif kit.cta_treatment == "minimal":
            draw.rounded_rectangle((48, btn_y, 672, btn_y + btn_height), radius=16, outline=accent, width=2)
            for idx, cl in enumerate(cta_lines):
                draw.text((76, btn_y + 20 + idx * 40), cl, font=cta_font, fill=foreground)
            draw.text((615, btn_y + 22), "→", font=_font(28, True, kit.font_family), fill=accent)
        else: # pill
            draw.rounded_rectangle((48, btn_y, 672, btn_y + btn_height), radius=btn_height // 2, fill=accent)
            for idx, cl in enumerate(cta_lines):
                bbox = draw.textbbox((0, 0), cl, font=cta_font)
                text_w = bbox[2] - bbox[0]
                draw.text(((720 - text_w) / 2, btn_y + 18 + idx * 40), cl, font=cta_font, fill="#111111")

        # Bottom safe zone reassurance
        draw.line([(48, 1140), (672, 1140)], fill="#242220", width=1)
        cta_path = os.path.join(output_dir, "brand_cta.png")
        cta_card.convert("RGB").save(cta_path, "PNG")
        cards.append(cta_path)

        return cards

    def _carousel_copy(self, campaign: Campaign) -> dict[str, object]:
        """Derive claim-safe carousel copy from the already approved campaign intelligence."""
        settings = self._campaign_copy(campaign)
        brief = campaign.brief
        direction = None
        if campaign.direction_set:
            direction = next(
                (item for item in campaign.direction_set.directions if item.direction_id == campaign.selected_direction_id),
                None,
            )

        research = campaign.research_pack
        problem_candidate = (
            (brief.audience_problem if brief else None)
            or (direction.core_tension if direction else None)
            or (research.audience_tensions[0] if research and research.audience_tensions else None)
            or (brief.subject_description if brief else None)
            or settings.caption
        )
        solution_candidate = (
            settings.caption
            or (brief.subject_description if brief else None)
            or (direction.creative_hypothesis if direction else None)
            or (research.creative_opportunity if research else None)
        )
        language = brief.output_language if brief else "en"
        subject_name = brief.subject_name if brief else ""
        display_subject = subject_name.split(":", 1)[0].strip()
        proof_heading = "Neden önemli?" if language == "tr" else "Why it matters"
        desired_feeling_copy = (brief.desired_feeling or "").strip() if brief else ""

        proof_items: list[str] = []
        candidates: list[str | None] = []
        if brief:
            candidates.extend(_requirement_customer_copy(value) for value in brief.must_include)
        candidates.extend([
            settings.caption,
            brief.subject_description if brief else None,
            desired_feeling_copy,
            brief.audience_problem if brief else None,
        ])
        for candidate in candidates:
            if (
                _contains_planning_language(candidate)
                or _contains_asset_inventory_language(candidate)
                or _contains_production_language(candidate)
            ):
                continue
            item = _shorten_copy(candidate, 82)
            if item and item.casefold() != settings.headline.casefold() and not any(
                _copy_is_similar(item, existing) for existing in proof_items
            ):
                proof_items.append(item)
        proof_items = proof_items[:3]

        return {
            "headline": settings.headline,
            "caption": settings.caption,
            "cta": settings.cta,
            "problem": _customer_facing_copy(problem_candidate, settings.caption or settings.headline, 120),
            "solution": _customer_facing_copy(solution_candidate, settings.caption or settings.headline, 108),
            "proof_heading": _customer_facing_copy(proof_heading, settings.headline, 72),
            "proof_items": proof_items,
        }

    def render_carousel_cards(
        self,
        background_bytes: bytes,
        campaign: Campaign,
        kit: BrandKit,
        logo_path: str | None,
        product_paths: list[str],
        output_dir: str,
    ) -> list[str]:
        """Render a five-card, manually swiped Instagram carousel at 1080x1350."""
        os.makedirs(output_dir, exist_ok=True)
        editorial_background = _safe_generated_background(background_bytes, (1080, 1350))
        foreground, background, accent = _palette_for(campaign, kit)
        copy = self._carousel_copy(campaign)
        language = campaign.brief.output_language if campaign.brief else "en"
        subject_name = campaign.brief.subject_name if campaign.brief else (kit.brand_name or "Your product")
        paths: list[str] = []

        def brand_canvas(use_editorial_background: bool = False) -> Image.Image:
            if use_editorial_background:
                canvas = editorial_background.copy()
                scrim = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                scrim_draw = ImageDraw.Draw(scrim)
                for y in range(1350):
                    alpha = int(60 + (y / 1350) * 150)
                    scrim_draw.line((0, y, 1080, y), fill=(8, 10, 18, alpha))
                canvas = Image.alpha_composite(canvas, scrim)
            else:
                canvas = Image.new("RGBA", (1080, 1350), background)
            self._draw_brand_lockup(canvas, kit, logo_path, foreground, accent, width=1080)
            return canvas

        def label(draw: ImageDraw.ImageDraw, index: int, text_tr: str, text_en: str, y: int = 175):
            value = text_tr if language == "tr" else text_en
            draw.rounded_rectangle((64, y, 330, y + 42), radius=10, fill=accent)
            draw.text((82, y + 10), f"{index:02d}  {value}", font=_font(16, True, kit.font_family), fill="#111111")

        def save(canvas: Image.Image, index: int, slug: str):
            path = os.path.join(output_dir, f"carousel_{index:02d}_{slug}.png")
            canvas.convert("RGB").save(path, "PNG")
            paths.append(path)

        # 1 — Hook / stop-scroll cover.
        canvas = brand_canvas(use_editorial_background=True)
        draw = ImageDraw.Draw(canvas)
        label(draw, 1, "KAPAK", "HOOK")
        headline_lines, headline_font = _fit_headline(
            str(copy["headline"]), kit.font_family, 952, 3, 78, 44,
            bold=kit.caption_preset != "editorial",
            italic=kit.caption_preset == "editorial",
        )
        y = 650
        for line in headline_lines:
            draw.text((64, y), line, font=headline_font, fill=foreground)
            y += int(headline_font.size * 1.18)
        caption = str(copy["caption"] or "")
        if caption.casefold().rstrip(".!?") == str(copy["headline"]).casefold().rstrip(".!?"):
            caption = ""
        if caption:
            caption_font = _font(31, False, kit.font_family)
            for line in _wrap_pixels(caption, caption_font, 900, 2):
                draw.text((64, y + 18), line, font=caption_font, fill="#E7E5E4")
                y += 42
        swipe = "Kaydır  >" if language == "tr" else "Swipe  >"
        draw.text((64, 1250), swipe, font=_font(22, True, kit.font_family), fill=accent)
        save(canvas, 1, "hook")

        # 2 — Audience problem, grounded in the brief/research rather than invented claims.
        canvas = brand_canvas()
        draw = ImageDraw.Draw(canvas)
        label(draw, 2, "İHTİYAÇ", "TENSION")
        problem_heading = "Bunu yaşayan yalnız değilsin." if language == "tr" else "This tension is familiar."
        draw.text((64, 285), problem_heading.upper(), font=_font(22, True, kit.font_family), fill=accent)
        problem_lines, problem_font = _fit_headline(
            str(copy["problem"]), kit.font_family, 900, 5, 58, 32, bold=True,
        )
        y = 360
        for line in problem_lines:
            draw.text((64, y), line, font=problem_font, fill=foreground)
            y += int(problem_font.size * 1.24)
        draw.rounded_rectangle((64, 1080, 1016, 1190), radius=22, outline=accent, width=3)
        bridge = "Sıradaki kartta çözümü gör." if language == "tr" else "See the product answer next."
        draw.text((96, 1116), bridge, font=_font(27, True, kit.font_family), fill=foreground)
        save(canvas, 2, "tension")

        # 3 — Exact product proof with the uploaded screenshot cleaned and framed.
        canvas = brand_canvas()
        draw = ImageDraw.Draw(canvas)
        label(draw, 3, "ÜRÜN", "PRODUCT")
        device_box = (555, 235, 990, 1050)
        self._draw_device_mockup(
            canvas,
            product_paths[0] if product_paths else None,
            device_box,
            accent,
            subject_name,
            kit.font_family,
        )
        draw.text((64, 310), subject_name.upper(), font=_font(21, True, kit.font_family), fill=accent)
        solution_lines, solution_font = _fit_headline(
            str(copy["solution"]), kit.font_family, 430, 7, 46, 28, bold=True,
        )
        y = 360
        for line in solution_lines:
            draw.text((64, y), line, font=solution_font, fill=foreground)
            y += int(solution_font.size * 1.22)
        save(canvas, 3, "product")

        # 4 — Three concise proof/value blocks from approved campaign context.
        canvas = brand_canvas()
        draw = ImageDraw.Draw(canvas)
        label(draw, 4, "ÖNE ÇIKANLAR", "WHY IT MATTERS")
        section_title = str(copy["proof_heading"])
        title_lines, title_font = _fit_headline(section_title, kit.font_family, 900, 2, 54, 36, bold=True)
        y = 285
        for line in title_lines:
            draw.text((64, y), line, font=title_font, fill=foreground)
            y += int(title_font.size * 1.2)
        for index, item in enumerate(copy["proof_items"]):
            top = 480 + index * 220
            card_fill = _mix_hex(background, foreground, 0.09)
            card_outline = _mix_hex(background, foreground, 0.22)
            draw.rounded_rectangle((64, top, 1016, top + 180), radius=24, fill=card_fill, outline=card_outline, width=2)
            draw.ellipse((94, top + 62, 142, top + 110), fill=accent)
            draw.text((109, top + 73), str(index + 1), font=_font(19, True, kit.font_family), fill="#111111")
            item_font = _font(28, True, kit.font_family)
            for line_index, line in enumerate(_wrap_pixels(str(item), item_font, 800, 3)):
                draw.text((174, top + 45 + line_index * 38), line, font=item_font, fill=foreground)
        save(canvas, 4, "proof")

        # 5 — Deterministic CTA card.
        canvas = brand_canvas()
        draw = ImageDraw.Draw(canvas)
        label(draw, 5, "HEMEN BAŞLA", "TAKE ACTION")
        draw.text((64, 330), subject_name.upper(), font=_font(24, True, kit.font_family), fill=accent)
        closing_lines, closing_font = _fit_headline(
            str(copy["headline"]), kit.font_family, 900, 3, 72, 42, bold=True,
        )
        y = 390
        for line in closing_lines:
            draw.text((64, y), line, font=closing_font, fill=foreground)
            y += int(closing_font.size * 1.2)
        cta_lines, cta_font = _fit_headline(str(copy["cta"]), kit.font_family, 760, 2, 48, 32, bold=True)
        button_top = 830
        draw.rounded_rectangle((64, button_top, 1016, button_top + 150), radius=34, fill=accent)
        cta_y = button_top + 35
        for line in cta_lines:
            bbox = draw.textbbox((0, 0), line, font=cta_font)
            draw.text(((1080 - (bbox[2] - bbox[0])) / 2, cta_y), line, font=cta_font, fill="#111111")
            cta_y += int(cta_font.size * 1.12)
        footer = "Profil bağlantısından ulaş." if language == "tr" else "Continue from the profile link."
        draw.text((64, 1045), footer, font=_font(28, False, kit.font_family), fill="#D6D3D1")
        draw.line((64, 1240, 1016, 1240), fill=accent, width=4)
        save(canvas, 5, "cta")

        return paths

    def compose_carousel_post(
        self,
        background_bytes: bytes,
        campaign: Campaign,
        kit: BrandKit,
        logo_path: str | None,
        product_paths: list[str],
        output_prefix: str,
    ) -> list[str]:
        """Render and upload an ordered five-slide carousel as individual PNG files."""
        with tempfile.TemporaryDirectory(prefix="reel_director_carousel_") as output_dir:
            paths = self.render_carousel_cards(
                background_bytes,
                campaign,
                kit,
                logo_path,
                product_paths,
                output_dir,
            )
            urls = []
            for index, path in enumerate(paths, start=1):
                filename = f"{output_prefix}_{index:02d}.png"
                urls.append(
                    ffmpeg_service.upload_to_gcs(
                        path,
                        f"final_posts/{filename}",
                        content_type="image/png",
                    )
                )
            return urls

    def compose_static_post(
        self,
        background_bytes: bytes,
        campaign: Campaign,
        kit: BrandKit,
        logo_path: str | None,
        product_paths: list[str],
        output_filename: str,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="reel_director_static_") as output_dir:
            canvas = _safe_generated_background(background_bytes, (1080, 1350))
            
            foreground, palette_background, accent = _palette_for(campaign, kit)
            treatment = getattr(campaign.production_settings, "visual_treatment", "brand_safe") if campaign.production_settings else "brand_safe"
            scrim_rgb = _rgb(palette_background)
            # Smooth treatment-aware gradient preserves imagery while keeping copy readable.
            scrim = Image.new("RGBA", (1080, 1350), (0, 0, 0, 0))
            scrim_draw = ImageDraw.Draw(scrim)
            for row in range(1350):
                if row < 400:
                    alpha = int((row / 400.0) * 45) # Gentle top darkening
                elif row < 700:
                    alpha = int(45 + ((row - 400) / 300.0) * 55) # Mid transition
                else:
                    alpha = int(100 + ((row - 700) / 650.0) * 115) # Max 215 at bottom
                if treatment == "high_contrast":
                    alpha = min(235, alpha + 18)
                elif treatment == "campaign_mood":
                    alpha = min(220, alpha + 6)
                scrim_draw.line([(0, row), (1080, row)], fill=(*scrim_rgb, alpha))
            canvas = Image.alpha_composite(canvas, scrim)

            draw = ImageDraw.Draw(canvas)
            settings = self._campaign_copy(campaign)
            subject_name = campaign.brief.subject_name if campaign.brief else (kit.brand_name or "Your product")

            # 1. Top Brand Lockup
            self._draw_brand_lockup(canvas, kit, logo_path, foreground, accent, width=1080)

            # 2. Product Showcase (Right-aligned device mockup or center inset)
            if product_paths:
                device_box = (640, 180, 1000, 720)
                self._draw_device_mockup(
                    canvas,
                    product_paths[0],
                    device_box,
                    accent,
                    subject_name,
                    kit.font_family,
                )

            # 3. Eyebrow Tag
            eyebrow_text = "ÖZEL TANITIM" if getattr(campaign.brief, 'output_language', 'en') == 'tr' else "FEATURED"
            draw.rounded_rectangle((64, 735, 230, 770), radius=6, fill="#221E1A")
            draw.text((76, 743), eyebrow_text, font=_font(14, True, kit.font_family), fill=accent)

            # 4. Large, crisp headline
            max_text_width = 952
            headline_lines, headline_font = _fit_headline(
                settings.headline,
                kit.font_family,
                max_width=max_text_width,
                max_lines=3,
                start_size=60,
                min_size=40,
                bold=kit.caption_preset != "editorial",
                italic=kit.caption_preset == "editorial"
            )
            y = 790
            for line in headline_lines:
                draw.text((64, y), line, font=headline_font, fill=foreground)
                y += int(headline_font.size * 1.22)

            # 5. Supporting caption
            supporting = settings.caption.strip() if settings.caption else ""
            if supporting and supporting != settings.headline and y < 1090:
                cap_font = _font(28, False, kit.font_family)
                for line in _wrap_pixels(supporting, cap_font, max_text_width, 2):
                    draw.text((64, y + 10), line, font=cap_font, fill="#D6D3D1")
                    y += 38

            # 6. Balanced CTA Button
            cta_y = max(y + 25, 1160)
            cta_font = _font(34, True, kit.font_family)
            cta_lines = _wrap_pixels(settings.cta, cta_font, 560, 2)
            btn_w = 480
            btn_h = 78
            
            if kit.cta_treatment == "card":
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=18, fill=accent)
                draw.text((96, cta_y + 18), cta_lines[0], font=cta_font, fill="#111111")
                draw.text((64 + btn_w - 48, cta_y + 18), "↗", font=_font(32, True, kit.font_family), fill="#111111")
            elif kit.cta_treatment == "minimal":
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=16, outline=accent, width=2)
                draw.text((96, cta_y + 18), cta_lines[0], font=cta_font, fill=foreground)
            else: # pill
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=btn_h // 2, fill=accent)
                bbox = draw.textbbox((0, 0), cta_lines[0], font=cta_font)
                text_w = bbox[2] - bbox[0]
                draw.text((64 + (btn_w - text_w) // 2, cta_y + 18), cta_lines[0], font=cta_font, fill="#111111")

            local_path = os.path.join(output_dir, output_filename)
            canvas.convert("RGB").save(local_path, "PNG")
            return ffmpeg_service.upload_to_gcs(local_path, f"final_posts/{output_filename}", content_type="image/png")

    def render_reel_cover(
        self,
        campaign: Campaign,
        kit: BrandKit,
        logo_path: str | None,
        product_paths: list[str],
        output_filename: str,
    ) -> str:
        """
        Deterministically produce a 1080x1920 Reel Cover PNG.
        All critical content is inside the centered 1080x1350 feed-safe zone.
        No Imagen-generated text. Logo, product proof, headline, CTA brand treatment.
        Returns proxy URL /api/media/covers/{filename}.
        """
        with tempfile.TemporaryDirectory(prefix="reel_director_cover_") as output_dir:
            canvas = Image.new("RGBA", (1080, 1920), (20, 18, 16, 255))
            draw = ImageDraw.Draw(canvas)

            foreground, background, accent = _palette_for(campaign, kit)

            # Fill background
            draw.rectangle((0, 0, 1080, 1920), fill=background)

            # Subtle top vignette accent bar
            draw.rounded_rectangle((64, 52, 1016, 56), radius=2, fill=accent)

            production_settings = self._campaign_copy(campaign)
            subject_name = campaign.brief.subject_name if campaign.brief else (kit.brand_name or "Brand")

            # === FEED-SAFE ZONE: 1080x1350 centered (top = 285, bottom = 1635) ===
            safe_top = 285
            safe_bottom = 1635

            # Safe-zone indicator (invisible in final but keeps layout honest)
            # All critical content between safe_top and safe_bottom

            # Brand lockup is intentionally inside the centered feed crop.
            self._draw_brand_lockup(
                canvas,
                kit,
                logo_path,
                foreground,
                accent,
                width=1080,
                top_y=safe_top + 24,
            )

            # Product device mockup if available - in center of safe zone
            if product_paths:
                device_top = safe_top + 120
                device_box = (260, device_top, 820, device_top + 610)
                self._draw_device_mockup(canvas, product_paths[0], device_box, accent, subject_name, kit.font_family)

            # Headline block - below device, inside safe zone. Do not leak
            # template taxonomy such as "Brand Reel" into customer-facing art.
            headline_y = safe_top + 760
            hl_y = headline_y
            headline_lines, headline_font = _fit_headline(
                production_settings.headline,
                kit.font_family,
                max_width=952,
                max_lines=2,
                start_size=72,
                min_size=48,
                bold=True,
            )
            for line in headline_lines:
                draw.text((64, hl_y), line, font=headline_font, fill=foreground)
                hl_y += int(headline_font.size * 1.2)

            # Supporting caption
            if production_settings.caption and hl_y < safe_bottom - 180:
                cap_font = _font(30, False, kit.font_family)
                for line in _wrap_pixels(production_settings.caption, cap_font, 952, 2):
                    draw.text((64, hl_y + 10), line, font=cap_font, fill="#A8A29E")
                    hl_y += 40

            # CTA button - inside safe zone, before safe_bottom
            cta_y = min(hl_y + 32, safe_bottom - 120)
            cta_font = _font(36, True, kit.font_family)
            cta_lines = _wrap_pixels(production_settings.cta, cta_font, 600, 2)
            btn_w = 560
            btn_h = 84

            if kit.cta_treatment == "card":
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=20, fill=accent)
                draw.text((96, cta_y + 20), cta_lines[0], font=cta_font, fill="#111111")
                draw.text((64 + btn_w - 52, cta_y + 22), "↗", font=_font(32, True, kit.font_family), fill="#111111")
            elif kit.cta_treatment == "minimal":
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=18, outline=accent, width=2)
                draw.text((96, cta_y + 20), cta_lines[0], font=cta_font, fill=foreground)
                draw.text((64 + btn_w - 52, cta_y + 22), "→", font=_font(30, True, kit.font_family), fill=accent)
            else:  # pill
                draw.rounded_rectangle((64, cta_y, 64 + btn_w, cta_y + btn_h), radius=btn_h // 2, fill=accent)
                bbox = draw.textbbox((0, 0), cta_lines[0], font=cta_font)
                text_w = bbox[2] - bbox[0]
                draw.text((64 + (btn_w - text_w) // 2, cta_y + 22), cta_lines[0], font=cta_font, fill="#111111")

            # Bottom brand bar (outside safe zone - invisible in feed but branded)
            draw.rounded_rectangle((64, 1680, 1016, 1684), radius=2, fill=accent)
            brand_bottom = (kit.brand_name or "REEL DIRECTOR").upper()
            draw.text((64, 1698), brand_bottom, font=_font(20, True, kit.font_family), fill=foreground)

            local_path = os.path.join(output_dir, output_filename)
            canvas.convert("RGB").save(local_path, "PNG")
            return ffmpeg_service.upload_to_gcs(local_path, f"final_covers/{output_filename}", content_type="image/png")


branded_finishing_service = BrandedFinishingService()
