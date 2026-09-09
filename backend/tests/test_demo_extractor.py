import pytest
from app.services.demo_extractor import extract_demo_brief, evaluate_demo_brief, detect_language
from app.services.mock_fixtures import (
    get_mock_research_plan,
    get_mock_research_pack,
    get_mock_direction_set,
    get_mock_shot_plan,
)


def test_english_brief_with_ascii_capital_i_stays_english():
    brief = extract_demo_brief(
        "Create an English Instagram campaign for LumaNote. Audience: young professionals. CTA: Install today."
    )

    assert brief.output_language == "en"


def test_turkish_demo_extraction():
    turkish_prompt = (
        "Masalcı, 4-9 yaş arası çocuklar için sakinleştirici ve eğitici sesli masallar sunan bir mobil uygulama. "
        "Hedef kitle ebeveynler. Amaç ücretsiz denemeyi başlatmak. Reklam dili Türkçe, sıcak ve güven veren olsun."
    )
    eval_res = evaluate_demo_brief(turkish_prompt)
    assert eval_res.is_sufficient is True
    assert eval_res.clarification_question is None

    brief = extract_demo_brief(turkish_prompt)
    assert brief.output_language == "tr"
    assert brief.subject_name == "Masalcı"
    assert "masallar" in brief.subject_description.lower()
    assert "ebeveynler" in brief.audience.lower()
    assert "ücretsiz deneme" in brief.goal.lower()
    assert "FocusFlow" not in brief.subject_name


def test_finansa_turkish_finance_brief_category_safe():
    prompt = (
        "Finansa, küçük işletmeler için nakit akışı takibi yapan bir finans uygulaması. "
        "Hedef kitle KOBİ sahipleri. Amaç ücretli abonelik başlatmak. Reklam dili Türkçe olsun."
    )
    brief = extract_demo_brief(prompt)
    assert brief.output_language == "tr"
    assert brief.subject_name == "Finansa"
    assert "kobi" in brief.audience.lower()
    assert "ücretli abonelik" in brief.goal.lower()

    # Verify fixtures are category safe - no child/story/bedtime/parent leaks
    r_plan = get_mock_research_plan(brief)
    r_pack = get_mock_research_pack(brief=brief)
    d_set = get_mock_direction_set(brief=brief)
    s_plan = get_mock_shot_plan(brief=brief)

    all_content = (
        str(r_plan.model_dump()) + " " +
        str(r_pack.model_dump()) + " " +
        str(d_set.model_dump()) + " " +
        str(s_plan.model_dump())
    ).lower()

    unwanted_terms = ["masal", "çocuk", "cocuk", "uyku", "bedtime", "ebeveyn", "parent", "ninni", "hikaye"]
    for term in unwanted_terms:
        assert term not in all_content, f"Leaked '{term}' in Finansa finance fixtures: {all_content}"


def test_glowmuse_english_skincare_brief_category_safe():
    prompt = (
        "GlowMuse is a vitamin C skincare serum for women aged 25-40. "
        "Goal: drive online purchases. Target audience: women aged 25-40."
    )
    brief = extract_demo_brief(prompt)
    assert brief.output_language == "en"
    assert brief.subject_name == "GlowMuse"
    assert "skincare" in brief.subject_description.lower() or "serum" in brief.subject_description.lower()
    assert "women" in brief.audience.lower()
    assert "purchases" in brief.goal.lower()

    # Verify fixtures are category safe - no focus/productivity/remote-worker/desk leaks
    r_plan = get_mock_research_plan(brief)
    r_pack = get_mock_research_pack(brief=brief)
    d_set = get_mock_direction_set(brief=brief)
    s_plan = get_mock_shot_plan(brief=brief)

    all_content = (
        str(r_plan.model_dump()) + " " +
        str(r_pack.model_dump()) + " " +
        str(d_set.model_dump()) + " " +
        str(s_plan.model_dump())
    ).lower()

    unwanted_terms = ["focus", "productivity", "remote worker", "context switch", "tabs", "deep work", "desk", "notification"]
    for term in unwanted_terms:
        assert term not in all_content, f"Leaked '{term}' in GlowMuse skincare fixtures: {all_content}"


def test_answer_clarification_data_flow_no_wrapper_leak():
    original_brief = "Masalcı"
    answer = "4-9 yaş çocuklar için sakinleştirici sesli masallar sunan bir mobil uygulama; hedef kitle ebeveynler; amaç ücretsiz denemeyi başlatmak."
    
    # Combined text with wrappers (like router builds)
    combined = f"Original Request: {original_brief}\nClarification Answer: {answer}"
    brief = extract_demo_brief(combined, original_brief=original_brief, answer=answer)
    
    assert brief.subject_name == "Masalcı", f"Expected 'Masalcı', got '{brief.subject_name}'"
    assert "Original Request" not in brief.subject_name
    assert "Clarification Answer" not in brief.subject_name
    assert "masallar" in brief.subject_description.lower()
    assert "ebeveynler" in brief.audience.lower()
    assert "ücretsiz deneme" in brief.goal.lower()
    assert brief.output_language == "tr"


def test_short_prompt_clarification():
    short_tr = "bir masal uygulaması"
    eval_tr = evaluate_demo_brief(short_tr)
    assert eval_tr.is_sufficient is False
    assert eval_tr.clarification_question is not None
    assert "Uygulamanız" in eval_tr.clarification_question

    short_en = "new app"
    eval_en = evaluate_demo_brief(short_en)
    assert eval_en.is_sufficient is False
    assert "Could you tell me" in eval_en.clarification_question
