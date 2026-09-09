from app.models.campaign import CampaignBrief, CreativeDirection
from app.services.gemini_service import GeminiService


def test_shot_plan_prompt_makes_customer_scene_requirements_override_direction():
    brief = CampaignBrief(
        subject_name="DreamLetter",
        subject_description="A private dream journal.",
        audience="Adults interested in dream reflection.",
        goal="App installs",
        must_include=[
            "Strict first-person falling POV followed by a hard cut to a woman waking before impact."
        ],
        must_avoid=["Impact, injury, gore, suicide, self-harm."],
        output_language="en",
    )
    conflicting_direction = CreativeDirection(
        direction_id="D1",
        name="Generic Search Results",
        hook="Tired of generic answers?",
        core_tension="Generic search results feel impersonal.",
        creative_hypothesis="Show a frustrated person searching on a phone.",
        visual_idea="A person scrolls generic search results on a phone.",
        cta_treatment="Download now.",
        evidence_ids=[],
        why_test="Common frustration.",
    )

    prompt = GeminiService.build_shot_plan_prompt(brief, conflicting_direction)

    assert "Must include` and `Must avoid` are binding production requirements" in prompt
    assert "ALL THREE Hybrid alternatives must depict that same required event" in prompt
    assert "Never replace a customer-mandated scene with generic product use, phone scrolling" in prompt
    assert "Strict first-person falling POV" in prompt
    assert "Impact, injury, gore, suicide, self-harm" in prompt
