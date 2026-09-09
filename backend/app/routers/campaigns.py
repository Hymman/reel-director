from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from app.dependencies import get_workspace_id
from app.models.campaign import Campaign, CampaignBrief, OutputFormat, ProductionSettings
from app.services.context_service import context_service
from app.services.library_store import asset_store, brand_kit_store
from app.models.library import BrandKit
from app.services.state_store import campaign_store, job_store
from app.models.job import Job
from app.services.mock_fixtures import get_mock_research_plan, get_mock_research_pack, get_mock_direction_set, get_mock_shot_plan
from app.services.demo_extractor import evaluate_demo_brief, extract_demo_brief
from app.services.parallel_service import parallel_service
from app.services.gemini_service import gemini_service
import time
import asyncio
import tempfile
from app.config import settings

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

def get_campaign_or_404(campaign_id: str, workspace_id: str):
    campaign = campaign_store.get(campaign_id)
    if not campaign or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _all_plan_shots(campaign: Campaign):
    if not campaign.shot_plan:
        return []
    return [*campaign.shot_plan.shots, *campaign.shot_plan.full_reel_shots]


def _format_shots(campaign: Campaign):
    if not campaign.shot_plan:
        return []
    if campaign.output_format == "full_video_reel":
        # Historical records did not have `full_reel_shots`; their original
        # hook/problem/payoff list remains a safe compatibility fallback.
        return campaign.shot_plan.full_reel_shots or campaign.shot_plan.shots
    return campaign.shot_plan.shots


def _default_production_settings(campaign: Campaign, selected_caption: str = "") -> ProductionSettings:
    direction = None
    if campaign.direction_set:
        direction = next(
            (item for item in campaign.direction_set.directions if item.direction_id == campaign.selected_direction_id),
            None,
        )
    kit = brand_kit_store.get(campaign.workspace_id) or BrandKit(workspace_id=campaign.workspace_id)
    output_language = campaign.brief.output_language if campaign.brief else "en"
    fallback_cta = "Daha fazla bilgi" if output_language == "tr" else "Learn more"
    default_product_ids = list(dict.fromkeys([
        *([kit.primary_product_asset_id] if kit.primary_product_asset_id else []),
        *kit.product_asset_ids,
    ]))[:3]
    return ProductionSettings(
        headline=(direction.hook if direction else (campaign.brief.subject_name if campaign.brief else ""))[:90],
        caption=selected_caption[:110],
        cta=((campaign.brief.cta if campaign.brief else None) or fallback_cta)[:48],
        audio_mode="native_ambient",
        product_asset_ids=default_product_ids,
        visual_treatment=kit.default_visual_treatment,
    )

from pydantic import BaseModel, Field
class CampaignSummary(BaseModel):
    id: str
    title: str
    stage: str
    updated_at: str
    output_exists: bool
    output_format: OutputFormat | None = None

@router.get("", response_model=list[CampaignSummary])
async def list_campaigns(workspace_id: str = Depends(get_workspace_id)):
    camps = [c for c in campaign_store.data.values() if getattr(c, "workspace_id", "legacy_workspace") == workspace_id]
    camps.sort(key=lambda c: getattr(c, "updated_at", ""), reverse=True)
    return [CampaignSummary(
        id=c.id,
        title=c.brief.subject_name if c.brief and hasattr(c.brief, 'subject_name') else 'Untitled Campaign',
        stage=c.stage,
        updated_at=getattr(c, "updated_at", ""),
        output_exists=bool(
            c.final_video_url
            or c.final_slideshow_url
            or c.final_image_url
            or c.final_carousel_urls
            or c.final_thumbnail_url
        ),
        output_format=c.output_format,
    ) for c in camps]

from pydantic import BaseModel
class ExtractBriefRequest(BaseModel):
    raw_text: str
    source_urls: list[str] = Field(default_factory=list, max_length=3)
    asset_ids: list[str] = Field(default_factory=list, max_length=12)


class RetryShotRequest(BaseModel):
    """Optional quality-control revision applied before a paid shot retry."""

    veo_prompt_intent: str | None = Field(default=None, min_length=40, max_length=1800)
    veo_audio_prompt: str | None = Field(default=None, min_length=10, max_length=700)
    negative_constraints: list[str] | None = Field(default=None, max_length=30)
    caption: str | None = Field(default=None, min_length=1, max_length=110)
    caption_start_seconds: float | None = Field(default=None, ge=0.0, le=8.0)
    first_frame_asset_id: str | None = Field(default=None, min_length=1, max_length=120)
    last_frame_asset_id: str | None = Field(default=None, min_length=1, max_length=120)

@router.post("/extract-brief")
async def extract_brief(req: ExtractBriefRequest, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    owned_assets = []
    for asset_id in req.asset_ids:
        asset = asset_store.get(asset_id)
        if not asset or asset.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Context asset not found")
        owned_assets.append(asset)
    try:
        safe_urls = [context_service.validate_url_syntax(url) for url in req.source_urls]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    campaign = Campaign(
        workspace_id=workspace_id,
        stage="intake",
        context_asset_ids=req.asset_ids,
        context_urls=safe_urls,
    )
    campaign_store.save(campaign.id, campaign)
    job = Job(workspace_id=workspace_id, campaign_id=campaign.id, stage="extracting", message="Evaluating brief...")
    job_store.save(job.job_id, job)
    
    async def run_extract(job_id, camp_id, text, urls, assets):
        try:
            media_analyzer = getattr(gemini_service, "analyze_media_assets", None)
            context_summary = await context_service.build_context(urls, assets, media_analyzer)
            contextual_text = text
            if context_summary:
                contextual_text = f"USER REQUEST:\n{text}\n\nREFERENCE CONTEXT:\n{context_summary}"
            campaign_store.update(camp_id, {"context_summary": context_summary})
            if settings.demo_mode:
                await asyncio.sleep(1)
                eval_res = evaluate_demo_brief(text)
                if not eval_res.is_sufficient and eval_res.clarification_question:
                    from app.models.campaign import IntakeState
                    intake_state = IntakeState(
                        clarification_question=eval_res.clarification_question,
                        clarification_count=1,
                        original_brief=text,
                        context_summary=context_summary
                    )
                    campaign_store.update(camp_id, {"intake_state": intake_state.model_dump(), "stage": "intake_clarification"})
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Clarification needed."})
                    return
                else:
                    brief = extract_demo_brief(text, context_summary)
                    if urls and not brief.source_url:
                        brief.source_url = urls[0]
                    image_asset = next((asset for asset in assets if asset.kind == "image"), None)
                    if image_asset and not brief.product_asset_uri:
                        brief.product_asset_uri = f"/api/assets/{image_asset.asset_id}/content"
                    campaign_store.update(camp_id, {"brief": brief.model_dump(), "stage": "brief_review"})
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Brief extracted."})
                    return
            else:
                eval_result = await gemini_service.evaluate_brief(contextual_text)
                if not eval_result.is_sufficient and eval_result.clarification_question:
                    from app.models.campaign import IntakeState
                    intake_state = IntakeState(clarification_question=eval_result.clarification_question, clarification_count=1, original_brief=text, context_summary=context_summary)
                    campaign_store.update(camp_id, {"intake_state": intake_state.model_dump(), "stage": "intake_clarification"})
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Clarification needed."})
                else:
                    job_store.update(job_id, {"progress": 50, "message": "Extracting structured brief..."})
                    brief = await gemini_service.extract_brief(contextual_text)
                    if urls and not brief.source_url:
                        brief.source_url = urls[0]
                    image_asset = next((asset for asset in assets if asset.kind == "image"), None)
                    if image_asset and not brief.product_asset_uri:
                        brief.product_asset_uri = f"/api/assets/{image_asset.asset_id}/content"
                    campaign_store.update(camp_id, {"brief": brief.model_dump(), "stage": "brief_review"})
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Brief extracted."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})
            
    background_tasks.add_task(run_extract, job.job_id, campaign.id, req.raw_text, safe_urls, owned_assets)
    return {"job_id": job.job_id, "campaign_id": campaign.id}

class AnswerClarificationRequest(BaseModel):
    answer: str

@router.post("/{campaign_id}/answer-clarification")
async def answer_clarification(campaign_id: str, req: AnswerClarificationRequest, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.intake_state:
        raise HTTPException(status_code=404)
    if campaign.intake_state.is_clarification_resolved:
        raise HTTPException(status_code=400, detail="Clarification has already been resolved")
        
    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="extracting", message="Processing clarification...")
    job_store.save(job.job_id, job)
    
    async def run_clarification(job_id, camp_id, answer):
        try:
            c = campaign_store.get(camp_id)
            if c.intake_state.clarification_count > 1:
                raise ValueError("Clarification limit exceeded")
            combined_text = f"{c.intake_state.original_brief}\n\n{answer}"
            if c.intake_state.context_summary:
                combined_text += f"\n\nReference Context:\n{c.intake_state.context_summary}"
            
            if settings.demo_mode:
                await asyncio.sleep(1)
                brief = extract_demo_brief(
                    combined_text,
                    context_summary=c.intake_state.context_summary,
                    original_brief=c.intake_state.original_brief,
                    answer=answer,
                )
            else:
                brief = await gemini_service.extract_brief(combined_text)
                
            c.intake_state.is_clarification_resolved = True
            campaign_store.update(camp_id, {"brief": brief.model_dump(), "intake_state": c.intake_state.model_dump(), "stage": "brief_review"})
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Brief extracted."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})
            
    background_tasks.add_task(run_clarification, job.job_id, campaign_id, req.answer)
    return {"job_id": job.job_id}

@router.post("/{campaign_id}/skip-clarification")
async def skip_clarification(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.intake_state:
        raise HTTPException(status_code=404)
    if campaign.intake_state.is_clarification_resolved:
        raise HTTPException(status_code=400, detail="Clarification has already been resolved")
        
    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="extracting", message="Extracting with original brief...")
    job_store.save(job.job_id, job)
    
    async def run_skip(job_id, camp_id):
        try:
            c = campaign_store.get(camp_id)
            if settings.demo_mode:
                await asyncio.sleep(1)
                extraction_text = c.intake_state.original_brief
                if c.intake_state.context_summary:
                    extraction_text += f"\n\nReference Context:\n{c.intake_state.context_summary}"
                brief = extract_demo_brief(extraction_text)
            else:
                extraction_text = c.intake_state.original_brief
                if c.intake_state.context_summary:
                    extraction_text += f"\n\nReference Context:\n{c.intake_state.context_summary}"
                brief = await gemini_service.extract_brief(extraction_text)
            
            c.intake_state.is_clarification_resolved = True
            campaign_store.update(camp_id, {"brief": brief.model_dump(), "intake_state": c.intake_state.model_dump(), "stage": "brief_review"})
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Brief extracted."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})
            
    background_tasks.add_task(run_skip, job.job_id, campaign_id)
    return {"job_id": job.job_id}

@router.post("/{campaign_id}/confirm-brief")
async def confirm_brief(campaign_id: str, brief: CampaignBrief, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    campaign_store.update(campaign_id, {"brief": brief.model_dump()})
    
    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="planning", message="Creating research plan...")
    job_store.save(job.job_id, job)
    
    async def run_plan(job_id, camp_id):
        try:
            c = campaign_store.get(camp_id)
            if settings.demo_mode:
                await asyncio.sleep(1)
                plan = get_mock_research_plan(c.brief)
            else:
                plan = await gemini_service.generate_research_plan(c.brief)
            campaign_store.update(camp_id, {"research_plan": plan.model_dump(), "stage": "research_plan"})
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Research plan ready."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})
            
    background_tasks.add_task(run_plan, job.job_id, campaign_id)
    return {"job_id": job.job_id}

@router.post("", response_model=Campaign)
def create_campaign(brief: CampaignBrief, workspace_id: str = Depends(get_workspace_id)):
    campaign = Campaign(workspace_id=workspace_id, brief=brief, stage="brief_review")
    campaign_store.save(campaign.id, campaign)
    return campaign

@router.get("/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    return campaign

@router.post("/{campaign_id}/research-plan")
async def generate_research_plan(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)

    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="planning", message="Building research plan...")
    job_store.save(job.job_id, job)
    
    async def run_plan(job_id, camp_id):
        try:
            c = campaign_store.get(camp_id)
            if settings.demo_mode:
                await asyncio.sleep(1)
                plan = get_mock_research_plan(c.brief)
            else:
                plan = await gemini_service.generate_research_plan(c.brief)
            campaign_store.update(camp_id, {"research_plan": plan.model_dump(), "stage": "research_plan"})
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Research plan ready."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})
            
    background_tasks.add_task(run_plan, job.job_id, campaign_id)
    return {"job_id": job.job_id}

@router.post("/{campaign_id}/research")
async def start_research(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)

    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="research", message="Starting live Parallel research...")
    job_store.save(job.job_id, job)

    async def run_live_research(job_id: str, camp_id: str):
        try:
            job_store.update(job_id, {"progress": 10, "message": "Querying Parallel Search API..."})
            camp = campaign_store.get(camp_id)
            # Pass the AI-generated plan to drive actual research (Fix 2)
            research_pack = await parallel_service.execute_research(camp.brief, camp.research_plan)
            
            job_store.update(job_id, {"progress": 60, "message": "Running Gemini claim verification..."})
            from app.services.claim_agent import claim_agent
            claim_verif = await claim_agent.verify_claims(str(camp.brief.model_dump()), research_pack.evidence)
            
            job_store.update(job_id, {"progress": 80, "message": "Synthesizing research with Gemini..."})
            from app.services.gemini_service import gemini_service
            synthesis = await gemini_service.synthesize_research(camp.brief, research_pack.evidence)
            
            research_pack.audience_tensions = synthesis.audience_tensions
            research_pack.format_patterns = synthesis.format_patterns
            research_pack.creative_opportunity = synthesis.creative_opportunity
            
            campaign_store.update(camp_id, {
                "stage": "research", 
                "research_pack": research_pack.model_dump(),
                "claim_verification": claim_verif
            })
            # The campaign is the durable workflow state. Persist it before the
            # job becomes observable as complete so the UI cannot fetch the
            # previous stage in the small completion race window.
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Research complete."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": f"Research failed: {str(e)}", "error_code": "RESEARCH_FAILED"})

    async def run_mock_research(job_id: str, camp_id: str):
        await asyncio.sleep(1)
        camp = campaign_store.get(camp_id)
        campaign_store.update(camp_id, {
            "stage": "research", 
            "research_pack": get_mock_research_pack(brief=camp.brief).model_dump()
        })
        job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Research complete."})

    if settings.demo_mode:
        background_tasks.add_task(run_mock_research, job.job_id, campaign_id)
    else:
        background_tasks.add_task(run_live_research, job.job_id, campaign_id)

    return {"job_id": job.job_id}

@router.post("/{campaign_id}/directions")
async def generate_directions(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.research_pack:
        raise HTTPException(status_code=400, detail="Research pack required before generating directions.")

    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="strategy", message="Generating creative directions...")
    job_store.save(job.job_id, job)

    async def run_live_directions(job_id: str, camp_id: str):
        try:
            job_store.update(job_id, {"progress": 10, "message": "Calling Gemini 2.5 Flash for strategy..."})
            camp = campaign_store.get(camp_id)
            
            # Since GeminiService has async method but google-genai is sync, we can just await it
            directions = await gemini_service.generate_directions(camp.brief, camp.research_pack)
            
            campaign_store.update(camp_id, {
                "stage": "directions", 
                "direction_set": directions.model_dump(),
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Directions ready."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": f"Strategy failed: {str(e)}", "error_code": "STRATEGY_FAILED"})

    async def run_mock_directions(job_id: str, camp_id: str):
        await asyncio.sleep(1)
        camp = campaign_store.get(camp_id)
        campaign_store.update(camp_id, {
            "stage": "directions", 
            "direction_set": get_mock_direction_set(brief=camp.brief).model_dump()
        })
        job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Directions ready."})

    if settings.demo_mode:
        background_tasks.add_task(run_mock_directions, job.job_id, campaign_id)
    else:
        background_tasks.add_task(run_live_directions, job.job_id, campaign_id)

    return {"job_id": job.job_id}

@router.post("/{campaign_id}/research/evidence/{evidence_id}/exclude")
def exclude_evidence(campaign_id: str, evidence_id: str, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.research_pack:
        raise HTTPException(status_code=404, detail="Research pack not found")
    
    found = False
    for item in campaign.research_pack.evidence:
        if item.evidence_id == evidence_id:
            item.excluded = True
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Evidence item not found")
        
    updated = campaign_store.update(campaign_id, {"research_pack": campaign.research_pack.model_dump()})
    return updated

@router.post("/{campaign_id}/directions/{direction_id}/select")
def select_direction(campaign_id: str, direction_id: str, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    
    updated = campaign_store.update(campaign_id, {"selected_direction_id": direction_id})
    return updated

@router.post("/{campaign_id}/shots/{shot_id}/select")
def select_shot(campaign_id: str, shot_id: str, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    
    if not campaign.shot_plan:
        raise HTTPException(status_code=400, detail="No shot plan available to select from.")
        
    shot_exists = any(s.shot_id == shot_id for s in campaign.shot_plan.shots)
    if not shot_exists:
        raise HTTPException(status_code=404, detail="Shot not found in this campaign.")
        
    # Prevent changing selection if any shot is currently in production or finished
    if any(s.status in ["queued", "generating", "ready"] for s in campaign.shot_plan.shots):
        raise HTTPException(status_code=400, detail="Cannot change selection after production has started.")
    
    selected_shot = next(s for s in campaign.shot_plan.shots if s.shot_id == shot_id)
    production_settings = campaign.production_settings or _default_production_settings(campaign)
    production_settings.caption = selected_shot.caption[:110]
    updated = campaign_store.update(campaign_id, {
        "selected_shot_id": shot_id,
        "production_settings": production_settings.model_dump(),
    })
    return updated

@router.post("/{campaign_id}/shot-plan")
async def generate_shot_plan(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)

    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="direction", message="Directing 3 candidate shots...")
    job_store.save(job.job_id, job)

    async def run_live_shot_plan(job_id: str, camp_id: str):
        try:
            job_store.update(job_id, {"progress": 20, "message": "Drafting shots with Gemini..."})
            c = campaign_store.get(camp_id)
            selected_id = c.selected_direction_id or "D1"
            
            # Find the selected direction
            selected_direction = None
            if c.direction_set:
                for d in c.direction_set.directions:
                    if d.direction_id == selected_id:
                        selected_direction = d
                        break
            
            if not selected_direction:
                raise ValueError("Selected direction not found")
                
            kit = brand_kit_store.get(c.workspace_id) or BrandKit(workspace_id=c.workspace_id)
            plan = await gemini_service.generate_shot_plan(
                c.brief,
                selected_direction,
                context_summary=c.context_summary,
                research=c.research_pack,
                brand_kit=kit,
            )
            production_settings = _default_production_settings(c)
            
            campaign_store.update(camp_id, {
                "stage": "studio", 
                "shot_plan": plan.model_dump(),
                "production_settings": production_settings.model_dump(),
                "selected_shot_id": None,
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Shot plan ready."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": str(e)})

    async def run_mock_shot_plan(job_id: str, camp_id: str):
        await asyncio.sleep(1)
        c = campaign_store.get(camp_id)
        selected_id = c.selected_direction_id or "D1"
        campaign_store.update(camp_id, {
            "stage": "studio",
            "shot_plan": get_mock_shot_plan(selected_id, brief=c.brief).model_dump(),
            "production_settings": _default_production_settings(c).model_dump(),
            "selected_shot_id": None,
        })
        job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Shot plan ready."})

    if settings.demo_mode:
        background_tasks.add_task(run_mock_shot_plan, job.job_id, campaign_id)
    else:
        background_tasks.add_task(run_live_shot_plan, job.job_id, campaign_id)

    return {"job_id": job.job_id}

from app.services.veo_service import veo_service
from app.services.ffmpeg_service import ffmpeg_service
from app.services.image_service import image_service
from app.services.branded_finishing import branded_finishing_service
from app.services.preview_service import preview_service


class OutputFormatRequest(BaseModel):
    output_format: OutputFormat


@router.post("/{campaign_id}/generate-previews")
async def generate_candidate_previews(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    """
    Idempotent: generate preview stills for the 3 Hybrid Reel candidate shots.
    Only generates for shots that don't already have preview_image_url.
    NEVER calls Veo. Returns job_id.
    """
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.shot_plan or not campaign.shot_plan.shots:
        raise HTTPException(status_code=400, detail="Shot plan required before generating previews.")

    # A fast reload can fire the automatic request more than once. Return the
    # active preview job instead of buying duplicate stills for the same plan.
    active_preview_job = next(
        (
            item
            for item in job_store.data.values()
            if item.campaign_id == campaign_id
            and item.workspace_id == workspace_id
            and item.stage not in ("complete", "failed")
            and "preview" in (item.message or "").casefold()
        ),
        None,
    )
    if active_preview_job:
        return {"job_id": active_preview_job.job_id}

    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="generating", message="Generating candidate previews...")
    job_store.save(job.job_id, job)

    async def run_previews(job_id: str, camp_id: str):
        try:
            c = campaign_store.get(camp_id)
            kit, logo_path, product_paths = _brand_context(c)
            shots_needing_preview = [s for s in c.shot_plan.shots if not s.preview_image_url]
            total = len(shots_needing_preview)
            if total == 0:
                job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Previews already generated."})
                return

            results = await preview_service.generate_previews_for_shots(
                shots_needing_preview, c, kit, logo_path, product_paths
            )

            # Refresh campaign and update preview URLs
            c = campaign_store.get(camp_id)
            updated_shots = False
            for shot in c.shot_plan.shots:
                if shot.shot_id in results:
                    shot.preview_image_url = results[shot.shot_id]
                    updated_shots = True
            if updated_shots:
                campaign_store.update(camp_id, {"shot_plan": c.shot_plan.model_dump()})

            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": f"Previews ready ({len(results)} stills)."})
        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": f"Preview generation failed: {str(e)}"})

    background_tasks.add_task(run_previews, job.job_id, campaign_id)
    return {"job_id": job.job_id}


@router.post("/{campaign_id}/output-format", response_model=Campaign)
def select_output_format(campaign_id: str, req: OutputFormatRequest, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if campaign.stage not in ("studio", "reel"):
        raise HTTPException(status_code=400, detail="Output format can only be changed in Director Studio or for a completed output")
    if any(shot.status in ["queued", "generating"] for shot in _all_plan_shots(campaign)):
        raise HTTPException(status_code=409, detail="Production is already in progress")
    updates = {"output_format": req.output_format}
    # A completed campaign may be reopened for deterministic repackaging. Existing
    # ready shots and final artifacts stay intact, so Campaign Pack can reuse them
    # without another paid video-generation call.
    if campaign.stage == "reel":
        updates["stage"] = "studio"
    # A user may produce the content-only formats after approving a paid shot,
    # then return to Campaign Pack. Preserve that locked ready-shot choice so
    # deterministic repackaging never strands the approved video or asks for a
    # second Veo call. Before production, content-only formats still clear an
    # ordinary tentative selection.
    has_locked_shot = any(shot.status in ("queued", "generating", "ready") for shot in _all_plan_shots(campaign))
    if req.output_format not in ("hybrid_reel", "campaign_pack") and not has_locked_shot:
        updates["selected_shot_id"] = None
    return campaign_store.update(campaign_id, updates)


@router.put("/{campaign_id}/production-settings", response_model=Campaign)
def update_production_settings(
    campaign_id: str,
    req: ProductionSettings,
    workspace_id: str = Depends(get_workspace_id),
):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if campaign.stage != "studio":
        raise HTTPException(status_code=400, detail="Production settings can only be edited in Director Studio")
    if any(shot.status in ["queued", "generating", "ready"] for shot in _all_plan_shots(campaign)):
        raise HTTPException(status_code=409, detail="Production settings are locked after production starts")
    req.headline = req.headline.strip()
    req.caption = req.caption.strip()
    req.cta = req.cta.strip()
    if not req.headline:
        raise HTTPException(status_code=400, detail="Headline is required")
    if not req.cta:
        raise HTTPException(status_code=400, detail="CTA is required")
    for asset_id in req.product_asset_ids:
        asset = asset_store.get(asset_id)
        if not asset or asset.workspace_id != workspace_id or asset.kind != "image":
            raise HTTPException(status_code=404, detail="Selected product image was not found in this workspace")
    return campaign_store.update(campaign_id, {"production_settings": req.model_dump()})


def _brand_context(campaign: Campaign):
    kit = brand_kit_store.get(campaign.workspace_id) or BrandKit(workspace_id=campaign.workspace_id)
    logo_path = None
    if kit.logo_asset_id:
        logo = asset_store.get(kit.logo_asset_id)
        if logo and logo.workspace_id == campaign.workspace_id and logo.kind == "image" and logo.storage_key:
            logo_path = logo.storage_key
    configured_product_ids = (
        campaign.production_settings.product_asset_ids
        if campaign.production_settings and campaign.production_settings.product_asset_ids
        else list(dict.fromkeys([
            *([kit.primary_product_asset_id] if kit.primary_product_asset_id else []),
            *kit.product_asset_ids,
        ]))
    )
    # A campaign may have persisted product proof while the Brand Kit roles were
    # accidentally reversed. Once the roles are corrected, never keep rendering
    # the exact Brand Logo as the hero product when a distinct Main Product exists.
    if (
        kit.logo_asset_id
        and kit.primary_product_asset_id
        and kit.logo_asset_id != kit.primary_product_asset_id
        and kit.logo_asset_id in configured_product_ids
    ):
        configured_product_ids = [
            kit.primary_product_asset_id if asset_id == kit.logo_asset_id else asset_id
            for asset_id in configured_product_ids
        ]
        configured_product_ids = list(dict.fromkeys(configured_product_ids))
    product_paths = []
    for asset_id in configured_product_ids[:3]:
        asset = asset_store.get(asset_id)
        if asset and asset.workspace_id == campaign.workspace_id and asset.kind == "image" and asset.storage_key:
            product_paths.append(asset.storage_key)
    return kit, logo_path, product_paths


def _shot_anchor_frame_path(campaign: Campaign, shot, field_name: str) -> str | None:
    asset_id = getattr(shot, field_name, None)
    if not asset_id:
        return None
    asset = asset_store.get(asset_id)
    if (
        not asset
        or asset.workspace_id != campaign.workspace_id
        or asset.kind != "image"
        or not asset.storage_key
    ):
        label = "first" if field_name == "first_frame_asset_id" else "last"
        raise ValueError(f"Shot {label}-frame asset is missing or outside this workspace")
    return asset.storage_key


def _shot_first_frame_path(campaign: Campaign, shot) -> str | None:
    return _shot_anchor_frame_path(campaign, shot, "first_frame_asset_id")


def _shot_last_frame_path(campaign: Campaign, shot) -> str | None:
    return _shot_anchor_frame_path(campaign, shot, "last_frame_asset_id")


def _start_veo_generation(campaign: Campaign, shot, audio_mode: str) -> str:
    """Preserve the historical provider call shape unless anchors exist."""
    kwargs = {"audio_mode": audio_mode}
    first_frame_path = _shot_first_frame_path(campaign, shot)
    if first_frame_path:
        kwargs["first_frame_path"] = first_frame_path
    last_frame_path = _shot_last_frame_path(campaign, shot)
    if last_frame_path:
        kwargs["last_frame_path"] = last_frame_path
    return veo_service.start_generation(shot, **kwargs)

@router.post("/{campaign_id}/produce")
async def start_production(campaign_id: str, background_tasks: BackgroundTasks, workspace_id: str = Depends(get_workspace_id)):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if campaign.output_format not in ("static_post", "carousel_post", "slideshow_reel") and not campaign.shot_plan:
        raise HTTPException(status_code=400, detail="Shot plan required before production.")
    if campaign.output_format in ("hybrid_reel", "campaign_pack") and not campaign.selected_shot_id:
        raise HTTPException(status_code=400, detail="A shot must be selected before production.")
    if campaign.output_format in ("hybrid_reel", "campaign_pack") and not any(s.shot_id == campaign.selected_shot_id for s in campaign.shot_plan.shots):
        raise HTTPException(status_code=400, detail="Selected shot not found in shot plan.")
    if campaign.output_format == "full_video_reel" and len(_format_shots(campaign)) < 2:
        raise HTTPException(status_code=400, detail="Full Video Reel requires at least two candidate shots.")
    production_settings = campaign.production_settings or _default_production_settings(campaign)
    if campaign.output_format in ("hybrid_reel", "campaign_pack") and not production_settings.caption.strip():
        selected = next(s for s in campaign.shot_plan.shots if s.shot_id == campaign.selected_shot_id)
        production_settings.caption = selected.caption[:110]
    if not production_settings.headline.strip() or not production_settings.cta.strip():
        raise HTTPException(status_code=400, detail="Review the headline and CTA before production.")
    campaign_store.update(campaign_id, {"production_settings": production_settings.model_dump()})
    campaign = campaign_store.get(campaign_id)

    if any(job.campaign_id == campaign_id and job.workspace_id == workspace_id and job.stage not in ["complete", "failed"] for job in job_store.data.values()):
        raise HTTPException(status_code=409, detail="Production is already in progress.")

    target_ids = set()
    format_shots = _format_shots(campaign)
    if campaign.output_format in ("hybrid_reel", "campaign_pack"):
        target_ids = {campaign.selected_shot_id}
    elif campaign.output_format == "full_video_reel":
        target_ids = {shot.shot_id for shot in format_shots[:3]}
    if target_ids:
        for shot in _all_plan_shots(campaign):
            if shot.shot_id in target_ids:
                # Repackaging an approved shot must never trigger another paid
                # generation. This supports both Campaign Pack completion and
                # deterministic Hybrid Reel finishing revisions.
                if campaign.output_format in ("hybrid_reel", "campaign_pack") and shot.status == "ready" and shot.video_url:
                    pass
                else:
                    shot.status = "queued"
                    shot.video_url = None
                    shot.operation_id = None
                    shot.error = None
            else:
                shot.status = "planned"
        campaign_store.update(campaign_id, {"shot_plan": campaign.shot_plan.model_dump()})

    if campaign.output_format == "static_post":
        message = "Generating Static Post..."
    elif campaign.output_format == "carousel_post":
        message = "Building five-card Carousel Post..."
    elif campaign.output_format == "slideshow_reel":
        message = "Building zero-Veo Slideshow Reel..."
    elif campaign.output_format == "campaign_pack":
        message = "Building Campaign Pack (Reels + Post + Carousel + Cover)..."
    else:
        message = "Submitting Veo 3.1 job..."
    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage="generating", message=message)
    job_store.save(job.job_id, job)

    async def run_live_production(job_id: str, camp_id: str):
        try:
            camp = campaign_store.get(camp_id)
            shot_plan = camp.shot_plan
            active_shots = _format_shots(camp)
            production_settings = camp.production_settings or _default_production_settings(camp)
            if camp.output_format in ("static_post", "carousel_post", "slideshow_reel"):
                job_store.update(job_id, {"progress": 20, "message": "Generating a shared editorial image background..."})
                direction = None
                if camp.direction_set:
                    direction = next((item for item in camp.direction_set.directions if item.direction_id == camp.selected_direction_id), None)
                prompt = (
                    "Create an abstract premium editorial mood texture, portrait 4:5. Background layer only: "
                    "no people, faces, hands, devices, phones, screens, UI, cards, buttons, icons, logos, "
                    "letters, numbers, typography, badges, claims, watermark or readable marks of any kind. "
                    "Use only atmospheric light, organic color gradients and subtle material texture. "
                    f"Product: {camp.brief.subject_name}. Audience: {camp.brief.audience}. "
                    f"Creative direction: {direction.visual_idea if direction else camp.brief.subject_description}. "
                    "Keep the center and lower third calm for a deterministic headline, exact product screenshot and CTA."
                )
                background = await image_service.generate_background(prompt)
                kit, logo_path, product_paths = _brand_context(camp)
                if camp.output_format == "static_post":
                    job_store.update(job_id, {"progress": 75, "stage": "assembling", "message": "Applying deterministic single-post layout..."})
                    final_image_url = branded_finishing_service.compose_static_post(
                        background,
                        camp,
                        kit,
                        logo_path,
                        product_paths,
                        f"post_{camp_id}.png",
                    )
                    campaign_store.update(camp_id, {
                        "stage": "reel",
                        "final_image_url": final_image_url,
                    })
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Static Post is ready."})
                    return

                if camp.output_format == "carousel_post":
                    job_store.update(job_id, {"progress": 65, "stage": "assembling", "message": "Composing five ordered carousel cards..."})
                    carousel_urls = branded_finishing_service.compose_carousel_post(
                        background,
                        camp,
                        kit,
                        logo_path,
                        product_paths,
                        f"carousel_{camp_id}",
                    )
                    campaign_store.update(camp_id, {
                        "stage": "reel",
                        "final_carousel_urls": carousel_urls,
                    })
                    job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Carousel Post is ready (5 cards)."})
                    return

                job_store.update(job_id, {"progress": 60, "stage": "assembling", "message": "Rendering branded slideshow cards..."})
                with tempfile.TemporaryDirectory(prefix="reel_director_slideshow_cards_") as card_dir:
                    card_paths = branded_finishing_service.render_carousel_cards(
                        background,
                        camp,
                        kit,
                        logo_path,
                        product_paths,
                        card_dir,
                    )
                    job_store.update(job_id, {"progress": 82, "message": "Animating cards into a 9:16 Slideshow Reel..."})
                    final_video_url = ffmpeg_service.assemble_slideshow_reel(
                        card_paths,
                        f"slideshow_{camp_id}.mp4",
                        motion_preset=kit.motion_preset,
                        audio_mode=production_settings.audio_mode,
                    )
                final_thumbnail_url = branded_finishing_service.render_reel_cover(
                    camp,
                    kit,
                    logo_path,
                    product_paths,
                    f"slideshow_cover_{int(time.time())}_{camp_id}.png",
                )
                campaign_store.update(camp_id, {
                    "stage": "reel",
                    "final_slideshow_url": final_video_url,
                    "final_thumbnail_url": final_thumbnail_url,
                })
                job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Slideshow Reel is ready."})
                return

            # --- Campaign Pack: 1 Veo (reuse if already ready) + post + cover ---
            if camp.output_format == "campaign_pack":
                selected_shot = next((s for s in active_shots if s.shot_id == camp.selected_shot_id), None)
                if not selected_shot:
                    job_store.update(job_id, {"stage": "failed", "message": "Selected shot not found."})
                    return

                # Step 1: Veo — only if not already ready
                if selected_shot.status == "ready" and selected_shot.video_url:
                    job_store.update(job_id, {"progress": 35, "message": "Reusing existing Veo shot (0 additional Veo calls)..."})
                else:
                    job_store.update(job_id, {"progress": 10, "message": "Sending Veo 3.1 job for campaign pack..."})
                    try:
                        op_name = _start_veo_generation(
                            camp,
                            selected_shot,
                            production_settings.audio_mode,
                        )
                        selected_shot.status = "generating"
                        selected_shot.operation_id = op_name
                        campaign_store.update(camp_id, {"shot_plan": shot_plan.model_dump()})
                        job_store.update(job_id, {"progress": 20, "message": "Waiting for Veo..."})
                        while True:
                            op_status = veo_service.check_operation(op_name)
                            if op_status["status"] == "completed":
                                selected_shot.status = "ready"
                                selected_shot.video_url = op_status["gcs_uri"]
                                break
                            elif op_status["status"] == "failed":
                                selected_shot.status = "failed"
                                selected_shot.error = op_status["error"]
                                break
                            await asyncio.sleep(5)
                        campaign_store.update(camp_id, {"shot_plan": shot_plan.model_dump()})
                    except Exception as e:
                        selected_shot.status = "failed"
                        selected_shot.error = str(e)
                        campaign_store.update(camp_id, {"shot_plan": shot_plan.model_dump()})

                if selected_shot.status != "ready":
                    job_store.update(job_id, {"stage": "failed", "message": "Veo generation failed.", "error_code": "VEO_FAILED"})
                    return

                kit, logo_path, product_paths = _brand_context(camp)

                # Step 2: build the reel when the pack is new/incomplete. A
                # retry with another pack artifact already present reuses the
                # successful reel and only fills what is missing.
                final_video_url = camp.final_video_url
                pack_has_artifact = bool(camp.final_image_url or camp.final_thumbnail_url)
                if not final_video_url or not pack_has_artifact:
                    job_store.update(job_id, {"progress": 50, "stage": "assembling", "message": "Assembling Hybrid Reel..."})
                    with tempfile.TemporaryDirectory(prefix="reel_director_pack_") as card_dir:
                        card_paths = branded_finishing_service.render_vertical_cards(camp, kit, logo_path, product_paths, card_dir)
                        final_video_url = ffmpeg_service.assemble_hybrid_reel(
                            selected_shot.video_url,
                            production_settings.caption or selected_shot.caption,
                            card_paths,
                            f"reel_{camp_id}.mp4",
                            motion_preset=kit.motion_preset,
                            font_family=kit.font_family,
                            caption_preset=kit.caption_preset,
                            audio_mode=production_settings.audio_mode,
                            caption_start_seconds=production_settings.caption_start_seconds,
                        )

                # Step 3: Reel Cover is deterministic and cheap. Persist it with
                # the reel before the external image call so a transient provider
                # failure can resume without reassembling the MP4.
                job_store.update(job_id, {"progress": 65, "message": "Composing Reel Cover..."})
                final_thumbnail_url = branded_finishing_service.render_reel_cover(
                    camp,
                    kit,
                    logo_path,
                    product_paths,
                    f"cover_{int(time.time())}_{camp_id}.png",
                )
                campaign_store.update(camp_id, {
                    "final_video_url": final_video_url,
                    "final_thumbnail_url": final_thumbnail_url,
                })

                # Step 4: one image background feeds Static Post, Carousel and
                # the zero-Veo Slideshow Reel. Existing successful artifacts are
                # reused on retry; missing formats are filled independently.
                direction = None
                if camp.direction_set:
                    direction = next((item for item in camp.direction_set.directions if item.direction_id == camp.selected_direction_id), None)
                post_prompt = (
                    "Abstract premium editorial mood texture, portrait 4:5. Background layer only: no people, "
                    "faces, hands, devices, phones, screens, UI, cards, buttons, icons, logos, letters, numbers, "
                    "typography, badges, claims, watermark or readable marks of any kind. Use only atmospheric "
                    "light, organic color gradients and subtle material texture. "
                    f"Product: {camp.brief.subject_name}. Audience: {camp.brief.audience}. "
                    f"Creative direction: {direction.visual_idea if direction else camp.brief.subject_description}. "
                    "Keep the center and lower third calm for deterministic layout."
                )
                final_image_url = camp.final_image_url
                final_carousel_urls = list(camp.final_carousel_urls)
                final_slideshow_url = camp.final_slideshow_url
                post_background = None
                if not final_image_url or not final_carousel_urls or not final_slideshow_url:
                    job_store.update(job_id, {"progress": 74, "message": "Generating one shared image background for the post formats..."})
                    post_background = await image_service.generate_background(post_prompt)

                if not final_image_url:
                    job_store.update(job_id, {"progress": 80, "stage": "assembling", "message": "Composing Static Post..."})
                    final_image_url = branded_finishing_service.compose_static_post(
                        post_background, camp, kit, logo_path, product_paths, f"post_{camp_id}.png"
                    )

                if not final_carousel_urls:
                    job_store.update(job_id, {"progress": 86, "stage": "assembling", "message": "Composing five-card Carousel Post..."})
                    final_carousel_urls = branded_finishing_service.compose_carousel_post(
                        post_background,
                        camp,
                        kit,
                        logo_path,
                        product_paths,
                        f"carousel_{camp_id}",
                    )

                if not final_slideshow_url:
                    job_store.update(job_id, {"progress": 92, "stage": "assembling", "message": "Animating the carousel into a Slideshow Reel..."})
                    with tempfile.TemporaryDirectory(prefix="reel_director_pack_slideshow_") as slideshow_dir:
                        slideshow_cards = branded_finishing_service.render_carousel_cards(
                            post_background,
                            camp,
                            kit,
                            logo_path,
                            product_paths,
                            slideshow_dir,
                        )
                        final_slideshow_url = ffmpeg_service.assemble_slideshow_reel(
                            slideshow_cards,
                            f"slideshow_{camp_id}.mp4",
                            motion_preset=kit.motion_preset,
                            audio_mode=production_settings.audio_mode,
                        )

                campaign_store.update(camp_id, {
                    "stage": "reel",
                    "final_video_url": final_video_url,
                    "final_slideshow_url": final_slideshow_url,
                    "final_image_url": final_image_url,
                    "final_carousel_urls": final_carousel_urls,
                    "final_thumbnail_url": final_thumbnail_url,
                })
                job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Campaign Pack is ready (2 Reels + Post + Carousel + Cover)."})
                return

            job_store.update(job_id, {"progress": 10, "message": "Sending Veo 3.1 Fast prompt with native audio..."})
            production_ids = {camp.selected_shot_id} if camp.output_format == "hybrid_reel" else {shot.shot_id for shot in active_shots[:3]}
            
            operations = {}
            for shot in active_shots:
                if shot.shot_id in production_ids:
                    if shot.status == "ready" and shot.video_url:
                        continue
                    try:
                        op_name = _start_veo_generation(
                            camp,
                            shot,
                            production_settings.audio_mode,
                        )
                        operations[shot.shot_id] = op_name
                        shot.status = "generating"
                        shot.operation_id = op_name
                    except Exception as e:
                        shot.status = "failed"
                        shot.error = str(e)
            
            campaign_store.update(camp_id, {"shot_plan": shot_plan.model_dump()})
            job_store.update(job_id, {"progress": 30, "message": "Waiting for Veo generation..."})

            # Poll for completion
            while True:
                for shot in active_shots:
                    if shot.status == "generating" and shot.shot_id in operations:
                        op_status = veo_service.check_operation(operations[shot.shot_id])
                        if op_status["status"] == "completed":
                            shot.status = "ready"
                            shot.video_url = op_status["gcs_uri"]
                        elif op_status["status"] == "failed":
                            shot.status = "failed"
                            shot.error = op_status["error"]
                
                campaign_store.update(camp_id, {"shot_plan": shot_plan.model_dump()})
                if not any(shot.status == "generating" and shot.shot_id in operations for shot in active_shots):
                    break
                    
                await asyncio.sleep(5)
            
            ready_shots = [shot for shot in active_shots if shot.shot_id in production_ids and shot.status == "ready"]
            minimum_ready = 1 if camp.output_format == "hybrid_reel" else 2
            if len(ready_shots) < minimum_ready:
                job_store.update(job_id, {"stage": "failed", "message": "Veo generation failed.", "error_code": "VEO_FAILED"})
                return

            job_store.update(job_id, {"progress": 90, "stage": "assembling", "message": "Applying branded finishing with FFmpeg..."})
            if camp.output_format == "hybrid_reel":
                selected_shot = ready_shots[0]
                kit, logo_path, product_paths = _brand_context(camp)
                with tempfile.TemporaryDirectory(prefix="reel_director_cards_") as card_dir:
                    card_paths = branded_finishing_service.render_vertical_cards(
                        camp,
                        kit,
                        logo_path,
                        product_paths,
                        card_dir,
                    )
                    final_url = ffmpeg_service.assemble_hybrid_reel(
                        selected_shot.video_url,
                        production_settings.caption or selected_shot.caption,
                        card_paths,
                        f"reel_{camp_id}.mp4",
                        motion_preset=kit.motion_preset,
                        font_family=kit.font_family,
                        caption_preset=kit.caption_preset,
                        audio_mode=production_settings.audio_mode,
                        caption_start_seconds=production_settings.caption_start_seconds,
                    )
            else:
                kit = brand_kit_store.get(camp.workspace_id) or BrandKit(workspace_id=camp.workspace_id)
                final_url = ffmpeg_service.assemble_reel(
                    [shot.video_url for shot in ready_shots],
                    [shot.caption for shot in ready_shots],
                    f"reel_{camp_id}.mp4",
                    cta_text=production_settings.cta,
                    font_family=kit.font_family,
                    caption_preset=kit.caption_preset,
                    audio_mode=production_settings.audio_mode,
                )
            
            campaign_store.update(camp_id, {
                "stage": "reel", 
                "final_video_url": final_url,
                "final_slideshow_url": None,
                "final_image_url": None,
                "final_carousel_urls": [],
                "final_thumbnail_url": None,
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Reel is ready."})

        except Exception as e:
            job_store.update(job_id, {"stage": "failed", "message": f"Production failed: {str(e)}", "error_code": "PRODUCTION_FAILED"})

    async def run_mock_production(job_id: str, camp_id: str):
        await asyncio.sleep(2)
        c = campaign_store.get(camp_id)
        if c.output_format == "static_post":
            campaign_store.update(camp_id, {
                "stage": "reel",
                "final_image_url": f"/api/media/posts/post_{camp_id}.png",
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Static Post is ready."})
            return
        if c.output_format == "carousel_post":
            campaign_store.update(camp_id, {
                "stage": "reel",
                "final_carousel_urls": [f"/api/media/posts/carousel_{camp_id}_{index:02d}.png" for index in range(1, 6)],
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Carousel Post is ready (5 cards)."})
            return
        if c.output_format == "slideshow_reel":
            campaign_store.update(camp_id, {
                "stage": "reel",
                "final_slideshow_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
                "final_thumbnail_url": f"/api/media/covers/slideshow_cover_{camp_id}.png",
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Slideshow Reel is ready."})
            return
        if c.output_format == "campaign_pack":
            job_store.update(job_id, {"progress": 40, "message": "Preparing Campaign Pack (demo)..."})
            # Mark selected shot as ready (reuse if already ready)
            if c.shot_plan:
                for s in _all_plan_shots(c):
                    if s.shot_id == c.selected_shot_id:
                        s.status = "ready"
                        if not s.video_url:
                            s.video_url = "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4"
                    elif s.shot_id != c.selected_shot_id:
                        if s.status not in ("ready",):
                            s.status = "planned"
                campaign_store.update(camp_id, {"shot_plan": c.shot_plan.model_dump()})
            await asyncio.sleep(2)
            campaign_store.update(camp_id, {
                "stage": "reel",
                "final_video_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
                "final_slideshow_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                "final_image_url": f"/api/media/posts/post_{camp_id}.png",
                "final_carousel_urls": [f"/api/media/posts/carousel_{camp_id}_{index:02d}.png" for index in range(1, 6)],
                "final_thumbnail_url": f"/api/media/covers/cover_{camp_id}.png",
            })
            job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Campaign Pack is ready."})
            return
        job_store.update(job_id, {"progress": 50, "message": "Generating video with native audio..."})
        mock_shots = _format_shots(c)
        mock_ids = {c.selected_shot_id} if c.output_format == "hybrid_reel" else {shot.shot_id for shot in mock_shots[:3]}
        if c.shot_plan:
            for s in _all_plan_shots(c):
                if s.shot_id in mock_ids:
                    s.status = "ready"
                    s.video_url = "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4"
                else:
                    s.status = "planned"
            campaign_store.update(camp_id, {"shot_plan": c.shot_plan.model_dump()})
            
        await asyncio.sleep(2)
        job_store.update(job_id, {"progress": 90, "stage": "assembling", "message": "Assembling reel with FFmpeg..."})
        await asyncio.sleep(2)
        campaign_store.update(camp_id, {
            "stage": "reel", 
            "final_video_url": "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
            "final_slideshow_url": None,
            "final_image_url": None,
            "final_carousel_urls": [],
            "final_thumbnail_url": None,
        })
        job_store.update(job_id, {"progress": 100, "stage": "complete", "message": "Reel is ready."})

    if settings.demo_mode:
        background_tasks.add_task(run_mock_production, job.job_id, campaign_id)
    else:
        background_tasks.add_task(run_live_production, job.job_id, campaign_id)

    return {"job_id": job.job_id}

@router.post('/{campaign_id}/shots/{shot_id}/retry')
async def retry_shot(
    campaign_id: str,
    shot_id: str,
    background_tasks: BackgroundTasks,
    req: RetryShotRequest | None = None,
    workspace_id: str = Depends(get_workspace_id),
):
    campaign = get_campaign_or_404(campaign_id, workspace_id)
    if not campaign.shot_plan:
        raise HTTPException(status_code=404, detail='Shot plan not found')
    if campaign.output_format in ('static_post', 'carousel_post', 'slideshow_reel'):
        raise HTTPException(status_code=400, detail='This output format has no Veo shot to retry')
    
    if campaign.output_format in ('hybrid_reel', 'campaign_pack') and not campaign.selected_shot_id:
        raise HTTPException(status_code=400, detail='No shot selected')
    
    if campaign.output_format in ('hybrid_reel', 'campaign_pack') and shot_id != campaign.selected_shot_id:
        raise HTTPException(status_code=400, detail='Cannot retry unselected shot')
        
    shot = next((s for s in _format_shots(campaign) if s.shot_id == shot_id), None)
    if not shot:
        raise HTTPException(status_code=404, detail='Shot not found')

    if req is not None:
        revision = req.model_dump(exclude_none=True)
        if "veo_prompt_intent" in revision:
            shot.veo_prompt_intent = revision["veo_prompt_intent"].strip()
        if "veo_audio_prompt" in revision:
            shot.veo_audio_prompt = revision["veo_audio_prompt"].strip()
        if "negative_constraints" in revision:
            shot.negative_constraints = [
                value.strip() for value in revision["negative_constraints"] if value.strip()
            ]
        if "first_frame_asset_id" in revision:
            first_frame = asset_store.get(revision["first_frame_asset_id"])
            if (
                not first_frame
                or first_frame.workspace_id != workspace_id
                or first_frame.kind != "image"
                or not first_frame.storage_key
            ):
                raise HTTPException(status_code=404, detail="First-frame image was not found in this workspace")
            shot.first_frame_asset_id = first_frame.asset_id
        if "last_frame_asset_id" in revision:
            last_frame = asset_store.get(revision["last_frame_asset_id"])
            if (
                not last_frame
                or last_frame.workspace_id != workspace_id
                or last_frame.kind != "image"
                or not last_frame.storage_key
            ):
                raise HTTPException(status_code=404, detail="Last-frame image was not found in this workspace")
            shot.last_frame_asset_id = last_frame.asset_id
        production_settings = campaign.production_settings or _default_production_settings(campaign, shot.caption)
        if "caption" in revision:
            shot.caption = revision["caption"].strip()
            production_settings.caption = shot.caption
        if "caption_start_seconds" in revision:
            production_settings.caption_start_seconds = revision["caption_start_seconds"]
        # Keep the rejected file privately auditable, but stop presenting it as
        # the campaign's current approved output while the revision is running.
        shot.status = "planned"
        shot.video_url = None
        shot.operation_id = None
        shot.error = None
        campaign = campaign_store.update(campaign_id, {
            "stage": "studio",
            "shot_plan": campaign.shot_plan.model_dump(),
            "production_settings": production_settings.model_dump(),
            "final_video_url": None,
        })
        
    job = Job(workspace_id=workspace_id, campaign_id=campaign_id, stage='generating', message=f'Retrying Veo 3.1 for {shot_id}...')
    job_store.save(job.job_id, job)
    
    async def run_retry(job_id: str, camp_id: str, s_id: str):
        try:
            job_store.update(job_id, {'progress': 10, 'message': 'Sending retry prompt to Veo...'})
            camp = campaign_store.get(camp_id)
            sp = camp.shot_plan
            active_shots = _format_shots(camp)
            production_settings = camp.production_settings or _default_production_settings(camp)
            target_shot = next((s for s in active_shots if s.shot_id == s_id), None)
            
            if settings.demo_mode:
                target_shot.status = 'generating'
                target_shot.operation_id = "mock-op-id"
                target_shot.error = None
                campaign_store.update(camp_id, {'shot_plan': sp.model_dump()})
                await asyncio.sleep(2)
                target_shot.status = 'ready'
                target_shot.video_url = "https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4"
                campaign_store.update(camp_id, {'shot_plan': sp.model_dump()})
            else:
                op_name = _start_veo_generation(
                    camp,
                    target_shot,
                    production_settings.audio_mode,
                )
                target_shot.status = 'generating'
                target_shot.operation_id = op_name
                target_shot.error = None
                campaign_store.update(camp_id, {'shot_plan': sp.model_dump()})
                
                job_store.update(job_id, {'progress': 30, 'message': 'Waiting for Veo...'})
                
                while True:
                    op_status = veo_service.check_operation(target_shot.operation_id)
                    if op_status['status'] == 'completed':
                        target_shot.status = 'ready'
                        target_shot.video_url = op_status['gcs_uri']
                        break
                    elif op_status['status'] == 'failed':
                        target_shot.status = 'failed'
                        target_shot.error = op_status['error']
                        break
                    await asyncio.sleep(5)
                    
                campaign_store.update(camp_id, {'shot_plan': sp.model_dump()})
            
            if target_shot.status == 'failed':
                job_store.update(job_id, {'stage': 'failed', 'message': f"Veo retry failed: {target_shot.error}"})
                return
            
            ready_shots = [item for item in active_shots if item.status == 'ready']
            selected_shot = next((s for s in ready_shots if s.shot_id == camp.selected_shot_id), None)
            can_assemble = bool(selected_shot) if camp.output_format == 'hybrid_reel' else len(ready_shots) >= 2
            if can_assemble:
                job_store.update(job_id, {'progress': 90, 'stage': 'assembling', 'message': 'Assembling final reel...'})
                if camp.output_format == 'hybrid_reel':
                    kit, logo_path, product_paths = _brand_context(camp)
                    with tempfile.TemporaryDirectory(prefix='reel_director_retry_cards_') as card_dir:
                        cards = branded_finishing_service.render_vertical_cards(camp, kit, logo_path, product_paths, card_dir)
                        final_url = ffmpeg_service.assemble_hybrid_reel(
                            selected_shot.video_url,
                            production_settings.caption or selected_shot.caption,
                            cards,
                            f'reel_{camp_id}.mp4',
                            motion_preset=kit.motion_preset,
                            font_family=kit.font_family,
                            caption_preset=kit.caption_preset,
                            audio_mode=production_settings.audio_mode,
                            caption_start_seconds=production_settings.caption_start_seconds,
                        )
                else:
                    kit = brand_kit_store.get(camp.workspace_id) or BrandKit(workspace_id=camp.workspace_id)
                    final_url = ffmpeg_service.assemble_reel(
                        [item.video_url for item in ready_shots[:3]],
                        [item.caption for item in ready_shots[:3]],
                        f'reel_{camp_id}.mp4',
                        cta_text=production_settings.cta,
                        font_family=kit.font_family,
                        caption_preset=kit.caption_preset,
                        audio_mode=production_settings.audio_mode,
                    )
                campaign_store.update(camp_id, {'stage': 'reel', 'final_video_url': final_url})
                job_store.update(job_id, {'progress': 100, 'stage': 'complete', 'message': 'Reel is ready.'})
            else:
                job_store.update(job_id, {'progress': 100, 'stage': 'complete', 'message': 'Shot retry complete.'})
                
        except Exception as e:
            # Mark shot as failed as well
            c = campaign_store.get(camp_id)
            if c:
                t = next((s for s in _all_plan_shots(c) if s.shot_id == s_id), None)
                if t:
                    t.status = 'failed'
                    campaign_store.update(camp_id, {'shot_plan': c.shot_plan.model_dump()})
            job_store.update(job_id, {'stage': 'failed', 'message': str(e)})

    background_tasks.add_task(run_retry, job.job_id, campaign_id, shot_id)
    return {'job_id': job.job_id}
