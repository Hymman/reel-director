import pytest
import asyncio
import tempfile
import os
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.state_store import JsonFileStore
from app.models.campaign import Campaign, CampaignBrief, ShotPlan, Shot
from app.models.job import Job
from app.services.mock_fixtures import get_mock_shot_plan
import app.services.veo_service as veo_service_module
import app.services.ffmpeg_service as ffmpeg_service_module
import app.routers.campaigns as campaigns_router
from unittest.mock import MagicMock

@pytest.fixture(autouse=True)
def isolated_stores(monkeypatch):
    from app.config import settings
    original_demo_mode = settings.demo_mode
    with tempfile.TemporaryDirectory() as tmpdir:
        camp_store = JsonFileStore(os.path.join(tmpdir, "campaigns.json"), Campaign)
        j_store = JsonFileStore(os.path.join(tmpdir, "jobs.json"), Job)
        monkeypatch.setattr(campaigns_router, "campaign_store", camp_store)
        monkeypatch.setattr(campaigns_router, "job_store", j_store)
        
        
        monkeypatch.setattr(ffmpeg_service_module.ffmpeg_service, "assemble_reel", MagicMock(return_value='http://test/reel.mp4'))
        monkeypatch.setattr(ffmpeg_service_module.ffmpeg_service, "assemble_hybrid_reel", MagicMock(return_value='http://test/reel.mp4'))

        try:
            yield camp_store, j_store
        finally:
            settings.demo_mode = original_demo_mode

@pytest.fixture
def mock_campaign(isolated_stores):
    camp_store, _ = isolated_stores
    sp = get_mock_shot_plan()
    for s in sp.shots:
        s.status = "planned"
        
    selected_shot_id = sp.shots[0].shot_id
    camp = Campaign(
        stage="studio",
        brief=CampaignBrief(subject_name="Test", subject_description="Desc", intent_type="promotion", audience="all", goal="go", cta="buy"),
        workspace_id="test_workspace",
        selected_shot_id=selected_shot_id,
        shot_plan=sp
    )
    camp_store.save(camp.id, camp)
    return camp

@pytest.mark.anyio
async def test_start_production_concurrency_and_veo_spy(mock_campaign, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import settings
    settings.demo_mode = False

    spy = MagicMock(return_value="mock_op_id")
    monkeypatch.setattr(veo_service_module.veo_service, "start_generation", spy)
    
    # Mock check_operation to return 'generating' once, then 'completed' to prevent hang
    def mock_check(*args, **kwargs):
        if getattr(mock_check, 'called', False):
            return {'status': 'completed', 'gcs_uri': 'test.mp4'}
        mock_check.called = True
        return {'status': 'generating'}
    monkeypatch.setattr(veo_service_module.veo_service, "check_operation", mock_check)
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        coro1 = client.post(f"/api/campaigns/{mock_campaign.id}/produce", headers={"X-Workspace-ID": "test_workspace"})
        coro2 = client.post(f"/api/campaigns/{mock_campaign.id}/produce", headers={"X-Workspace-ID": "test_workspace"})
        results = await asyncio.gather(coro1, coro2)
        
    statuses = [r.status_code for r in results]
    assert sorted(statuses) == [200, 409]
    assert spy.call_count == 1

@pytest.mark.anyio
async def test_retry_shot_negative(mock_campaign, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import settings
    settings.demo_mode = False

    spy = MagicMock(return_value="mock_op_id_retry")
    monkeypatch.setattr(veo_service_module.veo_service, "start_generation", spy)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unselected_id = mock_campaign.shot_plan.shots[1].shot_id
        res_neg = await client.post(f"/api/campaigns/{mock_campaign.id}/shots/{unselected_id}/retry", headers={"X-Workspace-ID": "test_workspace"})
        assert res_neg.status_code == 400
        assert "Cannot retry unselected shot" in res_neg.json()["detail"]
        assert spy.call_count == 0

@pytest.mark.anyio
async def test_retry_shot_success(mock_campaign, monkeypatch, isolated_stores):
    camp_store, j_store = isolated_stores
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import settings
    settings.demo_mode = False

    mock_campaign.shot_plan.shots[0].status = "failed"
    camp_store.update(mock_campaign.id, {"shot_plan": mock_campaign.shot_plan.model_dump()})

    spy = MagicMock(return_value="mock_op_id_retry")
    monkeypatch.setattr(veo_service_module.veo_service, "start_generation", spy)
    monkeypatch.setattr(veo_service_module.veo_service, "check_operation", MagicMock(return_value={'status': 'completed', 'gcs_uri': 'test.mp4'}))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"/api/campaigns/{mock_campaign.id}/shots/{mock_campaign.selected_shot_id}/retry", headers={"X-Workspace-ID": "test_workspace"})
        assert res.status_code == 200
        assert spy.call_count == 1
        
        await asyncio.sleep(0.5)
        
        c = camp_store.get(mock_campaign.id)
        assert c.shot_plan.shots[0].status == "ready"
        assert c.shot_plan.shots[1].status == "planned"
        assert c.shot_plan.shots[2].status == "planned"
        j = j_store.get(res.json()["job_id"])
        assert j.stage == "complete"

@pytest.mark.anyio
async def test_retry_shot_failure(mock_campaign, monkeypatch, isolated_stores):
    camp_store, j_store = isolated_stores
    monkeypatch.setenv("DEMO_MODE", "false")
    from app.config import settings
    settings.demo_mode = False

    mock_campaign.shot_plan.shots[0].status = "failed"
    camp_store.update(mock_campaign.id, {"shot_plan": mock_campaign.shot_plan.model_dump()})

    spy = MagicMock(return_value="mock_op_id_retry")
    monkeypatch.setattr(veo_service_module.veo_service, "start_generation", spy)
    monkeypatch.setattr(veo_service_module.veo_service, "check_operation", MagicMock(return_value={'status': 'failed', 'error': 'Veo error'}))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(f"/api/campaigns/{mock_campaign.id}/shots/{mock_campaign.selected_shot_id}/retry", headers={"X-Workspace-ID": "test_workspace"})
        assert res.status_code == 200
        
        await asyncio.sleep(0.5)
        
        c = camp_store.get(mock_campaign.id)
        assert c.shot_plan.shots[0].status == "failed"
        j = j_store.get(res.json()["job_id"])
        assert j.stage == "failed"
