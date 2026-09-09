from fastapi.testclient import TestClient
from app.main import app
from app.models.campaign import ResearchPack, CreativeDirectionSet

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_create_campaign():
    response = client.post("/api/campaigns", json={
        "subject_name": "FocusFlow",
        "subject_description": "AI Deep Work Assistant",
        "audience": "Remote Workers",
        "goal": "app_install",
        "platform": "instagram_reels",
        "tone": "energetic",
        "cta": "Try it free"
    }, headers={"X-Workspace-ID": "TEST_API_WORKSPACE"})
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["stage"] == "brief_review"

def test_schema_validation():
    # Test that empty evidence fails validation for ResearchPack
    try:
        ResearchPack(
            search_id="123",
            audience_tensions=["A"],
            desired_outcomes=["B"],
            format_patterns=["C"],
            creative_opportunities=["D"],
            evidence=[], # Can be empty, but must be valid
            research_summary="Sum"
        )
    except Exception as e:
        assert False, f"ResearchPack validation failed unexpectedly: {e}"

    # Test CreativeDirectionSet
    try:
        CreativeDirectionSet(
            directions=[],
            director_pick_direction_id="D1",
            director_pick_reason="Reason"
        )
    except Exception as e:
        assert False, f"CreativeDirectionSet validation failed unexpectedly: {e}"
