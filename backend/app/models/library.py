from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator
import uuid

from app.models.campaign import now_iso


AssetKind = Literal["image", "video", "pdf", "docx", "text", "url"]
VisualTreatment = Literal["brand_safe", "campaign_mood", "high_contrast"]


class BrandProfileProposal(BaseModel):
    """Editable first-draft brand choices proposed from trusted user context."""
    brand_voice: str = Field(default="Clear, confident, human", max_length=280)
    font_family: Literal["Inter", "Georgia", "Arial"] = "Inter"
    caption_preset: Literal["clean", "bold", "editorial"] = "clean"
    cta_treatment: Literal["pill", "card", "minimal"] = "pill"
    motion_preset: Literal["subtle", "dynamic", "none"] = "subtle"
    default_visual_treatment: VisualTreatment = "brand_safe"
    sample_headline: str = Field(default="", max_length=70)
    sample_caption: str = Field(default="", max_length=110)
    sample_cta: str = Field(default="", max_length=32)
    rationale: str = Field(default="", max_length=360)


class AssetRecord(BaseModel):
    asset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str
    name: str
    kind: AssetKind
    mime_type: str
    size_bytes: int = 0
    storage_key: Optional[str] = None
    source_url: Optional[str] = None
    extracted_text: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class AssetSummary(BaseModel):
    asset_id: str
    name: str
    kind: AssetKind
    mime_type: str
    size_bytes: int
    source_url: Optional[str] = None
    text_preview: str = ""
    created_at: str


class BrandKit(BaseModel):
    workspace_id: str
    brand_name: str = ""
    brand_voice: str = "Clear, confident, human"
    logo_asset_id: Optional[str] = None
    # The single product visual that should lead deterministic finishing.
    # Optional keeps every existing JSON record backward compatible.
    primary_product_asset_id: Optional[str] = None
    product_asset_ids: List[str] = Field(default_factory=list)
    brand_colors: List[str] = Field(default_factory=lambda: ["#F5F5F0", "#111111", "#7CFFB2"])
    font_family: str = "Inter"
    caption_preset: Literal["clean", "bold", "editorial"] = "clean"
    cta_treatment: Literal["pill", "card", "minimal"] = "pill"
    motion_preset: Literal["subtle", "dynamic", "none"] = "subtle"
    default_visual_treatment: VisualTreatment = "brand_safe"
    sample_headline: str = Field(default="", max_length=70)
    sample_caption: str = Field(default="", max_length=110)
    sample_cta: str = Field(default="", max_length=32)
    smart_profile_source: Literal["default", "gemini", "smart_fallback", "manual"] = "default"
    smart_profile_context_key: str = Field(default="", max_length=600)
    smart_profile_rationale: str = Field(default="", max_length=360)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def promote_legacy_product_role(self):
        """Treat the first historical product image as the explicit main product."""
        if not self.primary_product_asset_id and self.product_asset_ids:
            self.primary_product_asset_id = self.product_asset_ids[0]
            self.product_asset_ids = self.product_asset_ids[1:]
        return self
