from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone

OutputFormat = Literal[
    "hybrid_reel",
    "static_post",
    "carousel_post",
    "slideshow_reel",
    "full_video_reel",
    "campaign_pack",
]
AudioMode = Literal["native_ambient", "silent"]
VisualTreatment = Literal["brand_safe", "campaign_mood", "high_contrast"]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class CampaignBrief(BaseModel):
    campaign_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: Optional[str] = None
    intent_type: Literal["promotion", "topic"] = "promotion"
    subject_name: str
    subject_description: str
    source_url: Optional[str] = None
    audience: str
    audience_problem: Optional[str] = None
    desired_feeling: Optional[str] = None
    goal: str = "app_install"
    platform: str = "instagram_reels"
    tone: str = "energetic"
    cta: Optional[str] = "Try it free"
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)
    product_asset_uri: Optional[str] = None
    output_language: Literal["en", "tr"] = "en"

class ResearchPlan(BaseModel):
    research_objective: str
    target_audience: str
    research_questions: List[str]
    intent: str

class ClaimFlag(BaseModel):
    claim: str
    reason: str
    safer_wording_suggestion: str

class ClaimVerificationResult(BaseModel):
    unsupported_claims_found: bool
    flags: List[ClaimFlag] = Field(default_factory=list)

class EvidenceItem(BaseModel):
    evidence_id: str
    type: Literal["audience_language", "format_pattern", "category_observation", "desired_outcome"]
    claim: str
    excerpt: str
    source_title: str
    source_url: str
    published_at: Optional[str] = None
    presentation_label: Optional[str] = None
    excluded: bool = False

class SynthesizedResearch(BaseModel):
    audience_tensions: List[str]
    format_patterns: List[str]
    creative_opportunity: str

class ResearchPack(BaseModel):
    search_id: str
    query_count: int = 3
    audience_tensions: List[str] = Field(default_factory=list)
    format_patterns: List[str] = Field(default_factory=list)
    creative_opportunity: str = ""
    evidence: List[EvidenceItem]
    research_summary: str
    latency_seconds: Optional[float] = None

class CreativeDirection(BaseModel):
    direction_id: str
    name: str
    hook: str
    core_tension: str
    creative_hypothesis: str
    visual_idea: str
    cta_treatment: str
    evidence_ids: List[str]
    why_test: str
    director_score: float = 0.95

class CreativeDirectionSet(BaseModel):
    directions: List[CreativeDirection]
    director_pick_direction_id: str
    director_pick_reason: str

class Shot(BaseModel):
    shot_id: str
    order: int
    duration_seconds: int
    # `problem` remains accepted so older campaign JSON records still deserialize.
    # New Hybrid plans use `hero`; Full Reel plans use hook/body/payoff.
    purpose: Literal["hero", "hook", "body", "problem", "payoff"]
    creative_mode: Literal[
        "relatable_scenario",
        "creator_demo",
        "premium_metaphor",
        "sequential",
        "legacy",
    ] = "legacy"
    visual: str
    action: str
    camera: str
    audio_direction: str
    veo_audio_prompt: str = "Natural synchronized environmental ambience and realistic action sound effects. No dialogue, narration, or music lyrics."
    caption: str
    product_overlay: bool = False
    veo_prompt_intent: str
    negative_constraints: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    status: Literal["planned", "queued", "generating", "ready", "failed"] = "planned"
    error: Optional[str] = None
    operation_id: Optional[str] = None
    preview_image_url: Optional[str] = None
    # Optional workspace-owned still used as the exact opening frame for
    # image-to-video generation when shot geometry must be locked.
    first_frame_asset_id: Optional[str] = None
    # Optional workspace-owned still used as the exact final frame. Supplying
    # both anchors lets Veo interpolate a controlled camera move instead of
    # inventing an early scene transition.
    last_frame_asset_id: Optional[str] = None

class ShotPlan(BaseModel):
    direction_id: str
    aspect_ratio: str = "9:16"
    total_target_seconds: int = 18
    shots: List[Shot]
    # Hybrid `shots` are three equivalent hero alternatives. Full Reel uses this
    # separate sequential list. Empty keeps historical records readable.
    full_reel_shots: List[Shot] = Field(default_factory=list)


class ProductionSettings(BaseModel):
    headline: str = Field(default="", max_length=90)
    caption: str = Field(default="", max_length=110)
    # Allows the question/caption to enter after an opening visual beat instead
    # of covering the generated hook from frame one. Historical records keep
    # their existing behaviour through the zero-second default.
    caption_start_seconds: float = Field(default=0.0, ge=0.0, le=8.0)
    cta: str = Field(default="Learn more", max_length=48)
    audio_mode: AudioMode = "native_ambient"
    product_asset_ids: List[str] = Field(default_factory=list, max_length=3)
    visual_treatment: VisualTreatment = "brand_safe"

class IntakeState(BaseModel):
    clarification_question: Optional[str] = None
    is_clarification_resolved: bool = False
    clarification_count: int = 0
    original_brief: str = ""
    context_summary: str = ""

class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = "legacy_workspace"
    stage: Literal["intake", "intake_clarification", "brief_review", "research_plan", "research", "verification", "directions", "studio", "reel", "failed"] = "intake"
    intake_state: Optional[IntakeState] = None
    brief: Optional[CampaignBrief] = None
    research_plan: Optional[ResearchPlan] = None
    research_pack: Optional[ResearchPack] = None
    claim_verification: Optional[ClaimVerificationResult] = None
    direction_set: Optional[CreativeDirectionSet] = None
    selected_direction_id: Optional[str] = None
    shot_plan: Optional[ShotPlan] = None
    selected_shot_id: Optional[str] = None
    output_format: OutputFormat = "hybrid_reel"
    production_settings: Optional[ProductionSettings] = None
    context_asset_ids: List[str] = Field(default_factory=list)
    context_urls: List[str] = Field(default_factory=list)
    context_summary: str = ""
    final_video_url: Optional[str] = None
    final_slideshow_url: Optional[str] = None
    final_image_url: Optional[str] = None
    final_carousel_urls: List[str] = Field(default_factory=list)
    final_thumbnail_url: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
