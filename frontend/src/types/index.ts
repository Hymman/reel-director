export interface CampaignBrief {
  intent_type: "promotion" | "topic";
  subject_name: string;
  subject_description: string;
  source_url?: string;
  audience: string;
  goal: string;
  platform: string;
  tone: string;
  cta?: string;
  output_language?: 'en' | 'tr';
}

export interface EvidenceItem {
  evidence_id: string;
  type: string;
  claim: string;
  excerpt: string;
  source_title: string;
  source_url: string;
  presentation_label?: string;
  excluded: boolean;
}

export interface ResearchPack {
  search_id: string;
  audience_tensions: string[];
  format_patterns: string[];
  creative_opportunity: string;
  evidence: EvidenceItem[];
  research_summary: string;
  latency_seconds?: number;
}

export interface CreativeDirection {
  direction_id: string;
  name: string;
  hook: string;
  core_tension: string;
  creative_hypothesis: string;
  visual_idea: string;
  cta_treatment: string;
  evidence_ids: string[];
  why_test: string;
}

export interface CreativeDirectionSet {
  directions: CreativeDirection[];
  director_pick_direction_id: string;
  director_pick_reason: string;
}

export interface Shot {
  shot_id: string;
  order: number;
  duration_seconds: number;
  purpose: string;
  creative_mode?: 'relatable_scenario' | 'creator_demo' | 'premium_metaphor' | 'sequential' | 'legacy';
  visual: string;
  action: string;
  camera: string;
  audio_direction?: string;
  caption: string;
  product_overlay: boolean;
  veo_prompt_intent: string;
  status: string;
  video_url?: string;
  preview_image_url?: string;
}

export interface ShotPlan {
  direction_id: string;
  aspect_ratio: string;
  total_target_seconds: number;
  shots: Shot[];
  full_reel_shots?: Shot[];
}

export interface ProductionSettings {
  headline: string;
  caption: string;
  caption_start_seconds?: number;
  cta: string;
  audio_mode: 'native_ambient' | 'silent';
  product_asset_ids: string[];
  visual_treatment: 'brand_safe' | 'campaign_mood' | 'high_contrast';
}

export interface ResearchPlan {
  research_objective: string;
  target_audience: string;
  research_questions: string[];
  intent: string;
}

export interface ClaimFlag {
  claim: string;
  reason: string;
  safer_wording_suggestion: string;
}

export interface ClaimVerificationResult {
  unsupported_claims_found: boolean;
  flags: ClaimFlag[];
}

export interface IntakeState {
  clarification_question?: string;
  is_clarification_resolved: boolean;
  clarification_count?: number;
  original_brief: string;
  context_summary?: string;
}

export interface Campaign {
  id: string;
  stage: "intake" | "intake_clarification" | "brief_review" | "research_plan" | "research" | "verification" | "directions" | "studio" | "reel" | "failed";
  intake_state?: IntakeState;
  brief?: CampaignBrief;
  research_plan?: ResearchPlan;
  claim_verification?: ClaimVerificationResult;
  research_pack?: ResearchPack;
  direction_set?: CreativeDirectionSet;
  selected_direction_id?: string;
  shot_plan?: ShotPlan;
  selected_shot_id?: string;
  output_format?: OutputFormat;
  production_settings?: ProductionSettings;
  context_asset_ids?: string[];
  context_urls?: string[];
  context_summary?: string;
  final_video_url?: string;
  final_slideshow_url?: string;
  final_image_url?: string;
  final_carousel_urls?: string[];
  final_thumbnail_url?: string;
  created_at?: string;
  updated_at?: string;
}

export type OutputFormat = 'campaign_pack' | 'hybrid_reel' | 'static_post' | 'carousel_post' | 'slideshow_reel' | 'full_video_reel';

export type AssetKind = 'image' | 'video' | 'pdf' | 'docx' | 'text' | 'url';

export interface AssetSummary {
  asset_id: string;
  name: string;
  kind: AssetKind;
  mime_type: string;
  size_bytes: number;
  source_url?: string;
  text_preview: string;
  created_at: string;
}

export interface BrandKit {
  workspace_id: string;
  brand_name: string;
  brand_voice: string;
  logo_asset_id?: string;
  primary_product_asset_id?: string;
  product_asset_ids: string[];
  brand_colors: string[];
  font_family: string;
  caption_preset: 'clean' | 'bold' | 'editorial';
  cta_treatment: 'pill' | 'card' | 'minimal';
  motion_preset: 'subtle' | 'dynamic' | 'none';
  default_visual_treatment: 'brand_safe' | 'campaign_mood' | 'high_contrast';
  sample_headline: string;
  sample_caption: string;
  sample_cta: string;
  smart_profile_source: 'default' | 'gemini' | 'smart_fallback' | 'manual';
  smart_profile_context_key: string;
  smart_profile_rationale: string;
  created_at?: string;
  updated_at?: string;
}

export interface BrandKitSuggestion {
  brand_voice: string;
  brand_colors: string[];
  font_family: 'Inter' | 'Georgia' | 'Arial';
  caption_preset: 'clean' | 'bold' | 'editorial';
  cta_treatment: 'pill' | 'card' | 'minimal';
  motion_preset: 'subtle' | 'dynamic' | 'none';
  default_visual_treatment: 'brand_safe' | 'campaign_mood' | 'high_contrast';
  sample_headline: string;
  sample_caption: string;
  sample_cta: string;
  rationale: string;
  source: 'gemini' | 'smart_fallback';
  context_key: string;
}

export interface Job {
  job_id: string;
  campaign_id: string;
  stage: string;
  progress: number;
  message: string;
}
