import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from PIL import Image

from app.config import settings
from app.dependencies import get_workspace_id
from app.models.library import BrandKit, BrandProfileProposal
from app.services.gemini_service import gemini_service
from app.services.library_store import asset_store, brand_kit_store


router = APIRouter(prefix="/api/brand-kit", tags=["brand-kit"])


class PaletteExtractionRequest(BaseModel):
    asset_id: str


class PaletteExtractionResponse(BaseModel):
    colors: list[str]


class BrandKitSuggestionRequest(BaseModel):
    kit: BrandKit
    ui_language: Literal["en", "tr"] = "en"


class BrandKitSuggestion(BrandProfileProposal):
    brand_colors: list[str]
    source: Literal["gemini", "smart_fallback"]
    context_key: str


def validate_asset_ownership(asset_ids: list[str], workspace_id: str) -> None:
    for asset_id in asset_ids:
        asset = asset_store.get(asset_id)
        if not asset or asset.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Brand asset not found")


def _asset_name_has_any(asset_id: str | None, tokens: tuple[str, ...]) -> bool:
    if not asset_id:
        return False
    asset = asset_store.get(asset_id)
    if not asset:
        return False
    normalized = asset.name.casefold().replace("_", "-")
    return any(token in normalized for token in tokens)


def _roles_appear_swapped(kit: BrandKit) -> bool:
    """Catch only high-confidence filename contradictions, never ambiguous art direction."""
    if not kit.logo_asset_id or not kit.primary_product_asset_id:
        return False
    if kit.logo_asset_id == kit.primary_product_asset_id:
        return False
    product_tokens = ("screenshot", "screen-shot", "screen", "detail", "mockup", "capture", "ekran", "detay")
    logo_tokens = ("logo", "app-icon", "appicon", "icon", "monogram", "brand-mark", "simge")
    return (
        _asset_name_has_any(kit.logo_asset_id, product_tokens)
        and _asset_name_has_any(kit.primary_product_asset_id, logo_tokens)
    )


@router.get("", response_model=BrandKit)
def get_brand_kit(workspace_id: str = Depends(get_workspace_id)):
    return brand_kit_store.get(workspace_id) or BrandKit(workspace_id=workspace_id)


@router.put("", response_model=BrandKit)
def update_brand_kit(kit: BrandKit, workspace_id: str = Depends(get_workspace_id)):
    asset_ids = list(kit.product_asset_ids)
    if kit.logo_asset_id:
        asset_ids.append(kit.logo_asset_id)
    if kit.primary_product_asset_id:
        asset_ids.append(kit.primary_product_asset_id)
    validate_asset_ownership(asset_ids, workspace_id)
    if kit.logo_asset_id and asset_store.get(kit.logo_asset_id).kind != "image":
        raise HTTPException(status_code=400, detail="Logo must be an image asset")
    if kit.primary_product_asset_id and asset_store.get(kit.primary_product_asset_id).kind != "image":
        raise HTTPException(status_code=400, detail="Main product must be an image asset")
    for asset_id in kit.product_asset_ids:
        if asset_store.get(asset_id).kind != "image":
            raise HTTPException(status_code=400, detail="Supporting product visuals must be image assets")
    if _roles_appear_swapped(kit):
        raise HTTPException(
            status_code=400,
            detail="Brand Logo and Main Product appear swapped. Assign the logo/icon to Brand Logo and the product screenshot to Main Product.",
        )
    normalized_colors = []
    for color in kit.brand_colors[:5]:
        value = color.strip().upper()
        if len(value) != 7 or not value.startswith("#") or any(ch not in "0123456789ABCDEF" for ch in value[1:]):
            raise HTTPException(status_code=400, detail="Brand colors must use #RRGGBB")
        normalized_colors.append(value)
    kit.workspace_id = workspace_id
    kit.product_asset_ids = list(dict.fromkeys(
        asset_id for asset_id in kit.product_asset_ids
        if asset_id != kit.primary_product_asset_id
    ))[:3]
    kit.brand_colors = normalized_colors or ["#F5F5F0", "#111111", "#7CFFB2"]
    existing = brand_kit_store.get(workspace_id)
    if existing:
        kit.created_at = existing.created_at
        return brand_kit_store.update(workspace_id, kit.model_dump())
    brand_kit_store.save(workspace_id, kit)
    return kit


def _color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _extract_colors(storage_key: str) -> list[tuple[int, int, int]]:
    try:
        with Image.open(storage_key) as source:
            rgba = source.convert("RGBA")
            rgba.thumbnail((320, 320), Image.Resampling.LANCZOS)
            samples = []
            for red, green, blue, alpha in rgba.getdata():
                if alpha < 96:
                    continue
                brightness = (red + green + blue) / 3
                spread = max(red, green, blue) - min(red, green, blue)
                if brightness > 246 and spread < 16:
                    continue
                if brightness < 10:
                    continue
                samples.append((red, green, blue))
            if not samples:
                samples = [(245, 245, 240), (17, 17, 17), (124, 255, 178)]

            strip = Image.new("RGB", (len(samples), 1))
            strip.putdata(samples)
            # Keep enough clusters to preserve small but intentional accents (for
            # example a gold navigation icon) instead of only dominant surfaces.
            quantized = strip.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
            ranked = sorted(
                quantized.getcolors(maxcolors=256) or [],
                key=lambda item: item[0],
                reverse=True,
            )
            palette = quantized.getpalette() or []
            selected: list[tuple[int, int, int]] = []
            for _, index in ranked:
                offset = index * 3
                rgb = tuple(palette[offset:offset + 3])
                if len(rgb) != 3:
                    continue
                if all(_color_distance(rgb, existing) >= 42 for existing in selected):
                    selected.append(rgb)
                if len(selected) == 12:
                    break
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Image could not be read for palette extraction") from exc
    return selected


def _luminance(rgb: tuple[int, int, int]) -> float:
    return (0.2126 * rgb[0]) + (0.7152 * rgb[1]) + (0.0722 * rgb[2])


def _usable_palette(storage_keys: list[str]) -> list[str]:
    candidates: list[tuple[int, int, int]] = []
    for storage_key in storage_keys:
        for rgb in _extract_colors(storage_key):
            if all(_color_distance(rgb, existing) >= 36 for existing in candidates):
                candidates.append(rgb)
    if not candidates:
        candidates = [(245, 245, 240), (17, 17, 17), (124, 255, 178)]

    darkest = min(candidates, key=_luminance)
    lightest = max(candidates, key=_luminance)
    background = darkest if _luminance(darkest) < 105 else (17, 17, 17)
    foreground = lightest if _luminance(lightest) > 178 else (245, 245, 240)
    accent_candidates = [
        rgb for rgb in candidates
        if 65 <= _luminance(rgb) <= 225
        and max(rgb) - min(rgb) >= 30
        and _color_distance(rgb, background) >= 80
        and _color_distance(rgb, foreground) >= 45
    ]
    accent = max(
        accent_candidates or candidates,
        key=lambda rgb: ((max(rgb) - min(rgb)) * 2) + (55 if 85 <= _luminance(rgb) <= 205 else 0),
    )
    if _color_distance(accent, foreground) < 45 or _color_distance(accent, background) < 65:
        accent = (124, 255, 178)
    return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in (foreground, background, accent)]


def _selected_image_assets(kit: BrandKit, workspace_id: str) -> list[dict]:
    assets = []
    for role, asset_id in (("brand_logo", kit.logo_asset_id), ("main_product", kit.primary_product_asset_id)):
        if not asset_id:
            continue
        asset = asset_store.get(asset_id)
        if not asset or asset.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Brand asset not found")
        if asset.kind != "image" or not asset.storage_key or not os.path.isfile(asset.storage_key):
            raise HTTPException(status_code=400, detail="Brand suggestion requires available image assets")
        assets.append({"role": role, "name": asset.name, "mime_type": asset.mime_type, "path": asset.storage_key})
    return assets


def _brand_context_assets(workspace_id: str, brand_name: str):
    records = [
        asset for asset in asset_store.data.values()
        if asset.workspace_id == workspace_id and asset.kind in {"url", "text", "pdf", "docx"} and asset.extracted_text
    ]
    ordered = sorted(records, key=lambda asset: asset.created_at, reverse=True)
    brand_token = brand_name.strip().casefold()
    if len(brand_token) >= 3:
        related = [
            asset for asset in ordered
            if brand_token in f"{asset.name} {asset.source_url or ''} {asset.extracted_text}".casefold()
        ]
        return related[:4]
    return ordered[:1]


def _context_key(kit: BrandKit, context_assets) -> str:
    context_ids = ",".join(sorted(asset.asset_id for asset in context_assets))
    return "|".join([
        (kit.brand_name or "").strip().casefold(),
        kit.logo_asset_id or "",
        kit.primary_product_asset_id or "",
        context_ids,
    ])[:600]


def _fallback_profile(kit: BrandKit, ui_language: str) -> BrandProfileProposal:
    signal = f"{kit.brand_name} {kit.brand_voice} {kit.smart_profile_rationale}".casefold()
    premium = any(word in signal for word in ("premium", "editorial", "calm", "sakin", "mahrem", "düşünceli", "luxury", "zarif"))
    energetic = any(word in signal for word in ("energetic", "bold", "dynamic", "enerjik", "cesur", "hızlı", "spor"))
    brand = (kit.brand_name or ("Markanız" if ui_language == "tr" else "Your brand")).strip()
    if premium:
        choices = ("Georgia", "editorial", "pill", "subtle", "campaign_mood")
    elif energetic:
        choices = ("Inter", "bold", "card", "dynamic", "high_contrast")
    else:
        choices = ("Inter", "clean", "pill", "subtle", "brand_safe")
    if ui_language == "tr":
        generic_voice = kit.brand_voice.strip().casefold() in {"", "clear, confident, human", "açık, güven veren, samimi", "concise and practical"}
        voice = kit.brand_voice if not generic_voice else (
            "Sakin, düşünceli ve güven veren; mahremiyete saygılı, açık ve iddiasız." if premium
            else "Net, güven veren ve insani; kısa, özgün ve iddiasını kanıtla destekleyen."
        )
        headline, caption, cta = brand, "Net bir hikâye, tutarlı bir marka deneyimi.", "Keşfet"
        rationale = "Görsel varlıklardaki kontrast ve marka tonu, düzenlenebilir güvenli bir başlangıç sistemine dönüştürüldü."
    else:
        generic_voice = kit.brand_voice.strip().casefold() in {"", "clear, confident, human", "açık, güven veren, samimi", "concise and practical"}
        voice = kit.brand_voice if not generic_voice else (
            "Calm, thoughtful and reassuring; privacy-aware, clear and free of inflated claims." if premium
            else "Clear, confident and human; concise, distinctive and evidence-aware."
        )
        headline, caption, cta = brand, "A clear story with a consistent brand experience.", "Discover"
        rationale = "Visible contrast and brand tone were converted into a safe, editable starting system."
    return BrandProfileProposal(
        brand_voice=voice,
        font_family=choices[0],
        caption_preset=choices[1],
        cta_treatment=choices[2],
        motion_preset=choices[3],
        default_visual_treatment=choices[4],
        sample_headline=headline[:70],
        sample_caption=caption,
        sample_cta=cta,
        rationale=rationale,
    )


@router.post("/extract-palette", response_model=PaletteExtractionResponse)
def extract_palette(req: PaletteExtractionRequest, workspace_id: str = Depends(get_workspace_id)):
    """Extract a small, role-aware palette locally without an AI provider call."""
    asset = asset_store.get(req.asset_id)
    if not asset or asset.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Brand asset not found")
    if asset.kind != "image" or not asset.storage_key or not os.path.isfile(asset.storage_key):
        raise HTTPException(status_code=400, detail="Palette extraction requires an available image asset")
    return PaletteExtractionResponse(colors=_usable_palette([asset.storage_key]))


@router.post("/suggest", response_model=BrandKitSuggestion)
async def suggest_brand_kit(req: BrandKitSuggestionRequest, workspace_id: str = Depends(get_workspace_id)):
    """Prepare a professional first draft; user edits remain the final authority."""
    kit = req.kit
    image_assets = _selected_image_assets(kit, workspace_id)
    context_assets = _brand_context_assets(workspace_id, kit.brand_name)
    if not image_assets and not context_assets and not kit.brand_name.strip():
        raise HTTPException(status_code=400, detail="Add a brand name, URL, logo or main product first")

    storage_keys = [asset["path"] for asset in image_assets]
    palette = _usable_palette(storage_keys) if storage_keys else (kit.brand_colors or ["#F5F5F0", "#111111", "#7CFFB2"])
    context_text = "\n\n".join(asset.extracted_text[:2500] for asset in context_assets)
    proposal = None
    source: Literal["gemini", "smart_fallback"] = "smart_fallback"
    if not settings.demo_mode:
        try:
            proposal = await gemini_service.suggest_brand_profile(
                kit=kit,
                assets=image_assets,
                context_text=context_text,
                ui_language=req.ui_language,
            )
            source = "gemini"
        except Exception:
            proposal = None
    proposal = proposal or _fallback_profile(kit, req.ui_language)
    return BrandKitSuggestion(
        **proposal.model_dump(),
        brand_colors=palette[:3],
        source=source,
        context_key=_context_key(kit, context_assets),
    )
