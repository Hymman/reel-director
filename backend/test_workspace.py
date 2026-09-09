import pytest
import tempfile
import os
import json
import asyncio
import time
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.state_store import JsonFileStore
from app.models.campaign import Campaign, CampaignBrief, ShotPlan, Shot, IntakeState, ResearchPack, EvidenceItem, CreativeDirectionSet, CreativeDirection, ResearchPlan
from app.models.job import Job
import app.routers.campaigns as campaigns_router
import app.routers.jobs as jobs_router
import app.routers.media as media_router
import app.services.gemini_service as gemini_service_module

class FakeBlob:
    def __init__(self, data=b"FAKE_VIDEO_STREAM_DATA_1234567890"):
        self.data = data
        self.size = len(data)
    def exists(self):
        return True
    def reload(self):
        pass
    def download_as_bytes(self, start=None, end=None):
        if start is not None and end is not None:
            return self.data[start:end+1]
        return self.data

class FakeBucket:
    def __init__(self):
        self.requested_blob_names = []

    def blob(self, name):
        self.requested_blob_names.append(name)
        return FakeBlob()

@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch):
    from app.config import settings
    original_demo_mode = settings.demo_mode
    settings.demo_mode = False
    with tempfile.TemporaryDirectory() as tmpdir:
        camp_path = os.path.join(tmpdir, "campaigns.json")
        job_path = os.path.join(tmpdir, "jobs.json")
        camp_store = JsonFileStore(camp_path, Campaign)
        j_store = JsonFileStore(job_path, Job)
        monkeypatch.setattr(campaigns_router, "campaign_store", camp_store)
        monkeypatch.setattr(campaigns_router, "job_store", j_store)
        monkeypatch.setattr(jobs_router, "job_store", j_store)
        monkeypatch.setattr(media_router, "campaign_store", camp_store)
        
        # Mock Gemini
        class MockGemini:
            async def extract_brief(self, text):
                return CampaignBrief(subject_name="Mock", subject_description="Mock", audience="Mock", intent_type="promotion", goal="Mock", platform="Mock", tone="Mock", output_language="en")
            async def evaluate_brief(self, text):
                from collections import namedtuple
                Res = namedtuple('Res', ['is_sufficient', 'clarification_question'])
                return Res(True, None)
            async def generate_research_plan(self, brief):
                return ResearchPlan(research_objective="Obj", target_audience="Aud", research_questions=["q1"], intent="promotion")
            async def synthesize_research(self, brief, evidence):
                from app.models.campaign import SynthesizedResearch
                return SynthesizedResearch(audience_tensions=["T1"], format_patterns=["P1"], creative_opportunity="O1")
            async def generate_directions(self, brief, research):
                return CreativeDirectionSet(
                    directions=[CreativeDirection(direction_id="dir-1", name="D1", hook="H", core_tension="T", creative_hypothesis="CH", visual_idea="VI", cta_treatment="CTA", evidence_ids=["E1"], why_test="WT")],
                    director_pick_direction_id="dir-1",
                    director_pick_reason="Best hook"
                )
            async def generate_shot_plan(self, brief, direction):
                return ShotPlan(
                    direction_id=direction.direction_id,
                    aspect_ratio="9:16",
                    total_target_seconds=15,
                    shots=[
                        Shot(shot_id="s1", order=1, duration_seconds=5, purpose="hook", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v1", status="planned"),
                        Shot(shot_id="s2", order=2, duration_seconds=5, purpose="problem", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v2", status="planned"),
                        Shot(shot_id="s3", order=3, duration_seconds=5, purpose="payoff", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v3", status="planned"),
                    ]
                )
                
        monkeypatch.setattr(campaigns_router, "gemini_service", MockGemini())
        
        # Mock Veo
        class MockVeo:
            def __init__(self):
                self.start_generation_spy = MagicMock(return_value="mock_op_id")
            def start_generation(self, shot, audio_mode="native_ambient"):
                return self.start_generation_spy(shot, audio_mode=audio_mode)
            def check_operation(self, op_name):
                return {"status": "completed", "gcs_uri": "gs://mock_bucket/vid.mp4"}
                
        mock_veo = MockVeo()
        monkeypatch.setattr(campaigns_router, "veo_service", mock_veo)
        
        # Mock FFmpeg
        class MockFFmpeg:
            def __init__(self):
                self.assemble_spy = MagicMock(return_value="http://localhost:8000/api/media/reels/final_reel.mp4")
                self.bucket = FakeBucket()
            def assemble_reel(self, clips: list[str], texts: list[str], output_filename: str, cta_text: str = None, **kwargs) -> str:
                return self.assemble_spy(clips, texts, output_filename, cta_text, **kwargs)
            def assemble_hybrid_reel(self, selected_clip, caption, card_paths, output_filename, motion_preset="subtle", **kwargs) -> str:
                return self.assemble_spy([selected_clip], [caption], output_filename, motion_preset, **kwargs)
                
        mock_ffmpeg = MockFFmpeg()
        monkeypatch.setattr(campaigns_router, "ffmpeg_service", mock_ffmpeg)
        monkeypatch.setattr(media_router, "ffmpeg_service", mock_ffmpeg)
        
        try:
            yield camp_store, j_store, mock_veo, mock_ffmpeg, camp_path
        finally:
            settings.demo_mode = original_demo_mode

client = TestClient(app)

def test_headers_and_extract_and_create_workspace_inheritance(isolated_stores):
    camp_store, j_store, _, _, _ = isolated_stores
    
    # 1. Missing header -> 400
    res = client.get("/api/campaigns")
    assert res.status_code == 400
    
    # 2. Blank header -> 400
    res = client.get("/api/campaigns", headers={"X-Workspace-ID": "   "})
    assert res.status_code == 400
    
    # 3. extract-brief inherits workspace_id on both Campaign and Job
    res_extract = client.post("/api/campaigns/extract-brief", json={"raw_text": "Need a video for my app"}, headers={"X-Workspace-ID": "WS_ALPHA"})
    assert res_extract.status_code == 200
    camp_id = res_extract.json()["campaign_id"]
    job_id = res_extract.json()["job_id"]
    assert camp_store.get(camp_id).workspace_id == "WS_ALPHA"
    assert j_store.get(job_id).workspace_id == "WS_ALPHA"
    
    # 4. create-campaign inherits workspace_id
    res_create = client.post("/api/campaigns", json={"subject_name": "Direct App", "subject_description": "Desc", "audience": "Devs", "intent_type": "promotion", "goal": "install", "platform": "reels", "tone": "energetic"}, headers={"X-Workspace-ID": "WS_BETA"})
    assert res_create.status_code == 200
    camp_beta_id = res_create.json()["id"]
    assert camp_store.get(camp_beta_id).workspace_id == "WS_BETA"

    # 5. A/B list isolation
    res_list_alpha = client.get("/api/campaigns", headers={"X-Workspace-ID": "WS_ALPHA"})
    assert res_list_alpha.status_code == 200
    alpha_ids = [c["id"] for c in res_list_alpha.json()]
    assert camp_id in alpha_ids
    assert camp_beta_id not in alpha_ids

    res_list_beta = client.get("/api/campaigns", headers={"X-Workspace-ID": "WS_BETA"})
    assert res_list_beta.status_code == 200
    beta_ids = [c["id"] for c in res_list_beta.json()]
    assert camp_beta_id in beta_ids
    assert camp_id not in beta_ids

def test_all_mutations_and_jobs_cross_workspace_404(isolated_stores):
    camp_store, j_store, _, _, _ = isolated_stores
    
    camp_a = Campaign(
        workspace_id="WS_A",
        stage="brief_review",
        intake_state=IntakeState(original_brief="Raw", clarification_question="Why?"),
        brief=CampaignBrief(subject_name="Product A", subject_description="Desc", audience="Devs", intent_type="promotion", goal="install", platform="reels", tone="energetic", output_language="en"),
        research_pack=ResearchPack(
            search_id="sid_1",
            research_summary="Summary",
            evidence=[EvidenceItem(evidence_id="E1", claim="Claim 1", type="audience_language", source_title="T1", source_url="http://src", excerpt="Ex")],
            audience_tensions=["Ten 1"], format_patterns=["Pat 1"]
        ),
        direction_set=CreativeDirectionSet(
            directions=[CreativeDirection(direction_id="dir-1", name="D1", hook="H", core_tension="T", creative_hypothesis="CH", visual_idea="VI", cta_treatment="CTA", evidence_ids=["E1"], why_test="WT")],
            director_pick_direction_id="dir-1",
            director_pick_reason="Best hook"
        ),
        selected_direction_id="dir-1",
        shot_plan=ShotPlan(
            direction_id="dir-1", aspect_ratio="9:16", total_target_seconds=15,
            shots=[
                Shot(shot_id="s1", order=1, duration_seconds=5, purpose="hook", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v1", status="ready", video_url="http://vid1"),
                Shot(shot_id="s2", order=2, duration_seconds=5, purpose="problem", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v2", status="planned"),
                Shot(shot_id="s3", order=3, duration_seconds=5, purpose="payoff", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v3", status="planned"),
            ]
        ),
        selected_shot_id="s1"
    )
    camp_store.save(camp_a.id, camp_a)
    
    job_a = Job(workspace_id="WS_A", campaign_id=camp_a.id, stage="extracting", progress=50, message="Extracting...")
    j_store.save(job_a.job_id, job_a)

    headers_b = {"X-Workspace-ID": "WS_B"}

    # All mutations reject WS_B with 404
    assert client.get(f"/api/campaigns/{camp_a.id}", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/answer-clarification", json={"answer": "My answer"}, headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/skip-clarification", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/confirm-brief", json=camp_a.brief.model_dump(), headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/research", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/research/evidence/E1/exclude", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/directions", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/directions/dir-1/select", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/shot-plan", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/shots/s1/select", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/produce", headers=headers_b).status_code == 404
    assert client.post(f"/api/campaigns/{camp_a.id}/shots/s1/retry", headers=headers_b).status_code == 404
    assert client.get(f"/api/jobs/{job_a.job_id}", headers=headers_b).status_code == 404

def test_media_ownership_and_exact_filename_validation(isolated_stores):
    camp_store, _, _, mock_ffmpeg, _ = isolated_stores
    
    # 1. Campaign A with exact final_video_url
    camp_a = Campaign(
        workspace_id="WS_A",
        stage="reel",
        brief=CampaignBrief(subject_name="Media Test", subject_description="Desc", audience="Devs", intent_type="promotion", goal="install", platform="reels", tone="energetic"),
        final_video_url=""
    )
    exact_filename = f"reel_{camp_a.id}_final.mp4"
    camp_a.final_video_url = f"http://localhost:8000/api/media/reels/{exact_filename}"
    camp_store.save(camp_a.id, camp_a)

    headers_a = {"X-Workspace-ID": "WS_A"}
    headers_b = {"X-Workspace-ID": "WS_B"}

    # Correct file from A -> 200 (full) and 206 (Range)
    res_full = client.get(f"/api/media/reels/{exact_filename}", headers=headers_a)
    assert res_full.status_code == 200
    assert res_full.content == b"FAKE_VIDEO_STREAM_DATA_1234567890"

    res_range = client.get(f"/api/media/reels/{exact_filename}", headers={**headers_a, "Range": "bytes=0-9"})
    assert res_range.status_code == 206
    assert res_range.content == b"FAKE_VIDEO"

    # Workspace B accessing A's media -> 404
    blob_calls_before_denials = len(mock_ffmpeg.bucket.requested_blob_names)
    assert client.get(f"/api/media/reels/{exact_filename}", headers=headers_b).status_code == 404
    assert len(mock_ffmpeg.bucket.requested_blob_names) == blob_calls_before_denials

    # Missing header -> 400
    assert client.get(f"/api/media/reels/{exact_filename}").status_code == 400
    assert client.get(f"/api/media/reels/{exact_filename}", headers={"X-Workspace-ID": ""}).status_code == 400

    # Same workspace A, but requesting a different filename containing A's UUID -> 404
    wrong_filename = f"reel_{camp_a.id}_unauthorized.mp4"
    assert client.get(f"/api/media/reels/{wrong_filename}", headers=headers_a).status_code == 404
    assert len(mock_ffmpeg.bucket.requested_blob_names) == blob_calls_before_denials

    # Campaign with no final output (or None) -> 404
    camp_no_output = Campaign(
        workspace_id="WS_A",
        stage="brief_review",
        brief=CampaignBrief(subject_name="No Output", subject_description="Desc", audience="Devs", intent_type="promotion", goal="install", platform="reels", tone="energetic"),
        final_video_url=None
    )
    camp_store.save(camp_no_output.id, camp_no_output)
    no_output_filename = f"reel_{camp_no_output.id}.mp4"
    assert client.get(f"/api/media/reels/{no_output_filename}", headers=headers_a).status_code == 404
    assert len(mock_ffmpeg.bucket.requested_blob_names) == blob_calls_before_denials


def test_workspace_media_session_cookie_preserves_range_seek_without_query_identity(isolated_stores):
    camp_store, _, _, _, _ = isolated_stores
    campaign = Campaign(
        workspace_id="WS_COOKIE",
        stage="reel",
        brief=CampaignBrief(subject_name="Cookie Media", subject_description="Desc", audience="Devs", intent_type="promotion", goal="install", platform="reels", tone="energetic"),
    )
    filename = f"reel_{campaign.id}_cookie.mp4"
    campaign.final_video_url = f"/api/media/reels/{filename}"
    camp_store.save(campaign.id, campaign)

    with TestClient(app) as cookie_client:
        session_response = cookie_client.post("/api/workspace/session", headers={"X-Workspace-ID": "WS_COOKIE"})
        assert session_response.status_code == 200
        set_cookie = session_response.headers["set-cookie"].lower()
        assert "rd_workspace_id=ws_cookie" in set_cookie
        assert "httponly" in set_cookie
        assert "path=/api/media" in set_cookie

        range_response = cookie_client.get(f"/api/media/reels/{filename}", headers={"Range": "bytes=2-8"})
        assert range_response.status_code == 206
        assert range_response.headers["content-range"].startswith("bytes 2-8/")
        assert range_response.content == b"KE_VIDE"


def test_static_post_counts_as_campaign_output(isolated_stores):
    camp_store, _, _, _, _ = isolated_stores
    campaign = Campaign(
        workspace_id="WS_POST_SUMMARY",
        stage="reel",
        brief=CampaignBrief(subject_name="Static Ready", subject_description="Desc", audience="Creators", intent_type="promotion", goal="awareness", platform="instagram", tone="clear"),
        output_format="static_post",
    )
    campaign.final_image_url = f"/api/media/posts/post_{campaign.id}.png"
    camp_store.save(campaign.id, campaign)
    response = client.get("/api/campaigns", headers={"X-Workspace-ID": "WS_POST_SUMMARY"})
    assert response.status_code == 200
    assert response.json()[0]["output_exists"] is True


def test_built_frontend_and_spa_deep_links_are_served():
    root = client.get("/")
    deep_link = client.get("/campaigns/new")
    assert root.status_code == 200 and "Reel Director" in root.text
    assert deep_link.status_code == 200 and "Reel Director" in deep_link.text
    assert client.get("/api/not-a-real-route").status_code == 404

def test_production_and_retry_single_selected_shot(isolated_stores):
    camp_store, j_store, mock_veo, mock_ffmpeg, _ = isolated_stores
    headers_a = {"X-Workspace-ID": "WS_A"}

    sp = ShotPlan(
        direction_id="dir-1", aspect_ratio="9:16", total_target_seconds=15,
        shots=[
            Shot(shot_id="s1", order=1, duration_seconds=5, purpose="hook", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v1", status="planned"),
            Shot(shot_id="s2", order=2, duration_seconds=5, purpose="problem", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v2", status="planned"),
            Shot(shot_id="s3", order=3, duration_seconds=5, purpose="payoff", visual="v", action="a", camera="c", caption="c", audio_direction="a", product_overlay=False, veo_prompt_intent="v3", status="planned"),
        ]
    )
    camp = Campaign(
        workspace_id="WS_A",
        stage="studio",
        brief=CampaignBrief(subject_name="Test Product", subject_description="Desc", audience="Aud", intent_type="promotion", goal="goal", platform="reels", tone="energetic"),
        shot_plan=sp,
        selected_shot_id="s2"
    )
    camp_store.save(camp.id, camp)

    # 1. Produce
    res = client.post(f"/api/campaigns/{camp.id}/produce", headers=headers_a)
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    assert j_store.get(job_id).workspace_id == "WS_A"

    assert mock_veo.start_generation_spy.call_count == 1
    assert mock_veo.start_generation_spy.call_args[0][0].shot_id == "s2"
    assert mock_ffmpeg.assemble_spy.call_count == 1

    # 2. Retry on selected shot s2
    res_retry = client.post(f"/api/campaigns/{camp.id}/shots/s2/retry", headers=headers_a)
    assert res_retry.status_code == 200
    retry_job_id = res_retry.json()["job_id"]
    assert j_store.get(retry_job_id).workspace_id == "WS_A"
    assert mock_veo.start_generation_spy.call_count == 2
    assert mock_veo.start_generation_spy.call_args[0][0].shot_id == "s2"

    # 3. Retry on unselected shot s1 -> 400
    res_retry_bad = client.post(f"/api/campaigns/{camp.id}/shots/s1/retry", headers=headers_a)
    assert res_retry_bad.status_code == 400
    assert res_retry_bad.json()["detail"] == "Cannot retry unselected shot"

    # 4. A stale persisted selection that is absent from the plan is rejected
    # before any additional Veo call is scheduled.
    stale = Campaign(
        workspace_id="WS_A",
        stage="studio",
        brief=CampaignBrief(subject_name="Stale", subject_description="Desc", audience="Aud"),
        shot_plan=sp,
        selected_shot_id="missing-shot",
    )
    camp_store.save(stale.id, stale)
    calls_before_stale = mock_veo.start_generation_spy.call_count
    stale_res = client.post(f"/api/campaigns/{stale.id}/produce", headers=headers_a)
    assert stale_res.status_code == 400
    assert stale_res.json()["detail"] == "Selected shot not found in shot plan."
    assert mock_veo.start_generation_spy.call_count == calls_before_stale

def test_sidecar_file_persistence_and_turkish_output_language(isolated_stores):
    camp_store, _, _, _, camp_file_path = isolated_stores
    headers = {"X-Workspace-ID": "WS_TR"}

    # Inject legacy raw data
    camp_store.raw_data["legacy_raw_1"] = {
        "id": "legacy_raw_1",
        "stage": "intake",
        "some_custom_legacy_field": "do_not_touch_value"
    }
    camp_store.data["legacy_raw_1"] = Campaign.model_validate(camp_store.raw_data["legacy_raw_1"])
    camp_store.save("legacy_raw_1", camp_store.data["legacy_raw_1"])

    # Create campaign with Turkish output language via confirm-brief
    camp = Campaign(
        workspace_id="WS_TR",
        stage="brief_review",
        brief=CampaignBrief(subject_name="TR App", subject_description="Desc", audience="Devs", intent_type="promotion", goal="install", platform="reels", tone="energetic", output_language="tr")
    )
    camp_store.save(camp.id, camp)

    # Confirm brief with Turkish
    res_confirm = client.post(f"/api/campaigns/{camp.id}/confirm-brief", json=camp.brief.model_dump(), headers=headers)
    assert res_confirm.status_code == 200
    
    # Verify campaign now has Turkish output language
    res_get = client.get(f"/api/campaigns/{camp.id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["brief"]["output_language"] == "tr"

    # Read back directly from store and file reload
    new_store = JsonFileStore(camp_file_path, Campaign)
    c_loaded = new_store.get(camp.id)
    assert c_loaded.brief.output_language == "tr"


def test_raw_sidecar_preserves_unrelated_legacy_record_and_timestamps(tmp_path):
    camp_file_path = tmp_path / "campaigns.json"
    legacy_raw = {
        "id": "legacy_raw_1",
        "stage": "intake",
        "some_custom_legacy_field": "do_not_touch_value",
    }
    camp_file_path.write_text(json.dumps({"legacy_raw_1": legacy_raw}), encoding="utf-8")
    store = JsonFileStore(str(camp_file_path), Campaign)

    first = Campaign(workspace_id="WS_TIME", brief=CampaignBrief(subject_name="First", subject_description="D", audience="A"))
    store.save(first.id, first)
    first_created = store.get(first.id).created_at
    first_updated = store.get(first.id).updated_at
    raw_legacy_before = dict(store.raw_data["legacy_raw_1"])

    time.sleep(0.002)
    second = Campaign(workspace_id="WS_TIME", brief=CampaignBrief(subject_name="Second", subject_description="D", audience="A"))
    store.save(second.id, second)
    second_raw_before = dict(store.raw_data[second.id])
    time.sleep(0.002)
    store.update(first.id, {"stage": "brief_review"})

    assert store.get(first.id).created_at == first_created
    assert store.get(first.id).updated_at > first_updated
    assert store.raw_data[second.id] == second_raw_before
    assert store.raw_data["legacy_raw_1"] == raw_legacy_before == legacy_raw

    reloaded = JsonFileStore(str(camp_file_path), Campaign)
    assert reloaded.raw_data["legacy_raw_1"] == legacy_raw
    assert "workspace_id" not in reloaded.raw_data["legacy_raw_1"]


def test_descending_campaign_summaries_and_legacy_hidden(isolated_stores):
    camp_store, _, _, _, _ = isolated_stores
    headers = {"X-Workspace-ID": "WS_SORT"}
    older = Campaign(workspace_id="WS_SORT", brief=CampaignBrief(subject_name="Older", subject_description="D", audience="A"))
    camp_store.save(older.id, older)
    time.sleep(0.002)
    newer = Campaign(workspace_id="WS_SORT", brief=CampaignBrief(subject_name="Newer", subject_description="D", audience="A"))
    camp_store.save(newer.id, newer)
    legacy = Campaign(brief=CampaignBrief(subject_name="Legacy Hidden", subject_description="D", audience="A"))
    camp_store.save(legacy.id, legacy)

    response = client.get("/api/campaigns", headers=headers)
    assert response.status_code == 200
    summaries = response.json()
    assert [item["id"] for item in summaries] == [newer.id, older.id]
    assert all(item["id"] != legacy.id for item in summaries)
    assert summaries[0]["title"] == "Newer"
    assert summaries[0]["output_exists"] is False

def test_all_four_prompt_builders_contain_explicit_directives_for_both_en_and_tr():
    from app.services.gemini_service import GeminiService
    service = GeminiService()
    
    spy_gen = MagicMock()
    mock_models = MagicMock()
    mock_models.generate_content = spy_gen
    mock_client = MagicMock()
    mock_client.aio.models = mock_models
    service.client = mock_client
    
    brief_en = CampaignBrief(subject_name="App EN", subject_description="Desc", audience="Aud", intent_type="promotion", goal="goal", platform="reels", tone="energetic", output_language="en")
    brief_tr = CampaignBrief(subject_name="App TR", subject_description="Desc", audience="Aud", intent_type="promotion", goal="goal", platform="reels", tone="energetic", output_language="tr")
    
    research_pack = ResearchPack(
        search_id="s1", research_summary="Sum",
        evidence=[EvidenceItem(evidence_id="E1", claim="C", excerpt="Ex", source_title="T", source_url="U", type="audience_language")],
        audience_tensions=["T1"], format_patterns=["P1"]
    )
    direction = CreativeDirection(direction_id="dir-1", name="D", hook="H", core_tension="CT", creative_hypothesis="CH", visual_idea="VI", cta_treatment="CTA", evidence_ids=["E1"], why_test="WT")

    async def run_checks():
        # 1. generate_research_plan
        try: await service.generate_research_plan(brief_en)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in en" in spy_gen.call_args_list[-1][1]["contents"]

        try: await service.generate_research_plan(brief_tr)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in tr" in spy_gen.call_args_list[-1][1]["contents"]

        # 2. synthesize_research
        try: await service.synthesize_research(brief_en, research_pack.evidence)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in en" in spy_gen.call_args_list[-1][1]["contents"]

        try: await service.synthesize_research(brief_tr, research_pack.evidence)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in tr" in spy_gen.call_args_list[-1][1]["contents"]

        # 3. generate_directions
        try: await service.generate_directions(brief_en, research_pack)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in en" in spy_gen.call_args_list[-1][1]["contents"]

        try: await service.generate_directions(brief_tr, research_pack)
        except Exception: pass
        assert "CRITICAL OUTPUT REQUIREMENT: Produce ALL natural language text in tr" in spy_gen.call_args_list[-1][1]["contents"]

        # 4. generate_shot_plan
        try: await service.generate_shot_plan(brief_en, direction)
        except Exception: pass
        prompt = spy_gen.call_args_list[-1][1]["contents"]
        assert "User-visible fields" in prompt and "English (en)" in prompt
        assert "Internal fields" in prompt and "MUST be in English" in prompt

        try: await service.generate_shot_plan(brief_tr, direction)
        except Exception: pass
        prompt = spy_gen.call_args_list[-1][1]["contents"]
        assert "User-visible fields" in prompt and "Turkish (tr)" in prompt
        assert "Internal fields" in prompt and "MUST be in English" in prompt

    asyncio.run(run_checks())
