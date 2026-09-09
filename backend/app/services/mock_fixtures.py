from typing import Optional
from app.models.campaign import (
    CampaignBrief,
    ResearchPlan,
    ResearchPack,
    EvidenceItem,
    CreativeDirection,
    CreativeDirectionSet,
    ShotPlan,
    Shot,
)


def get_mock_research_plan(brief: Optional[CampaignBrief] = None) -> ResearchPlan:
    subject = brief.subject_name if brief and brief.subject_name else "Product"
    desc = brief.subject_description if brief and brief.subject_description else "solution and service"
    audience = brief.audience if brief and brief.audience else "Target Audience"
    goal = brief.goal if brief and brief.goal else "Drive adoption"
    is_tr = brief and getattr(brief, "output_language", "en") == "tr"

    if is_tr:
        return ResearchPlan(
            research_objective=f"{subject} ({desc}) için hedef kitlenin ({audience}) temel motivasyonlarını ve pazar fırsatlarını araştırmak.",
            target_audience=audience,
            research_questions=[
                f"{subject} kullanıcı geri bildirimleri ve deneyimleri nelerdir?",
                f"{audience} için en etkili kısa video reklam formatları hangileridir?",
                f"{subject} ile {goal.lower()} hedefine ulaşmak için öne çıkan kancalar nelerdir?",
            ],
            intent=getattr(brief, "intent_type", "promotion"),
        )
    return ResearchPlan(
        research_objective=f"Investigate core motivations of {audience} to formulate high-converting reel concepts for {subject} ({desc}).",
        target_audience=audience,
        research_questions=[
            f"What are the primary feedback points and pain points for {audience}?",
            f"What short-form social video formats convert best for {subject}?",
            f"Which core value propositions drive {goal.lower()} most effectively?",
        ],
        intent=getattr(brief, "intent_type", "promotion"),
    )


def get_mock_research_pack(search_id: str = "par_123456789", brief: Optional[CampaignBrief] = None) -> ResearchPack:
    subject = brief.subject_name if brief and brief.subject_name else "Product"
    desc = brief.subject_description if brief and brief.subject_description else "solution"
    audience = brief.audience if brief and brief.audience else "Target Audience"
    goal = brief.goal if brief and brief.goal else "Drive conversion"
    is_tr = brief and getattr(brief, "output_language", "en") == "tr"

    if is_tr:
        return ResearchPack(
            search_id=search_id,
            audience_tensions=[
                f"{audience}, mevcut yetersiz yöntemler ve zaman kaybı nedeniyle güvenilir bir çözüm arıyor. [E1]",
                f"{subject} gibi net değer sağlayan yenilikler karmaşık alternatiflerin önüne geçiyor. [E2]",
                f"Doğrudan {goal.lower()} yönünde sonuç veren pratik deneyimler tercih ediliyor. [E1]",
            ],
            desired_outcomes=[
                f"{subject} ile {goal.lower()}.".replace("..", "."),
                f"{audience} için güvenilir ve pratik bir deneyim yaşamak.",
            ],
            format_patterns=[
                "POV + problemden çözüme hızlı geçiş + doğrudan kanca. [E2]",
                "Günlük hayattan samimi ve kanıt odaklı kullanım anları. [E1]",
                "Öncesi ve sonrası somut sonuç karşılaştırması. [E2]",
            ],
            creative_opportunity=f"{subject} ile hedef kitleye ({audience}) somut değer sunarak {goal.lower()}. [E1] [E2]".replace("..", "."),
            evidence=[
                EvidenceItem(
                    evidence_id="E1",
                    type="audience_language",
                    claim=f"{audience} doğrudan sonuca ulaştıran pratik çözümleri tercih ediyor.",
                    excerpt=f"{subject} gibi net ve güvenilir bir deneyim arayışı içindeyiz.",
                    source_title="Sektörel Kullanıcı İçgörüleri",
                    source_url="https://community.feedback.local/tr",
                    presentation_label="Kaynak 1",
                ),
                EvidenceItem(
                    evidence_id="E2",
                    type="format_pattern",
                    claim="Yüksek performanslı reklamlarda ilk 3 saniyede net fayda gösteriliyor.",
                    excerpt="İlk saniyelerde somut değer kancası sunan reklamlar 2 kat daha yüksek dönüşüm sağlıyor.",
                    source_title="Sosyal Reklam Analiz Raporu",
                    source_url="https://ads.analysis.local/tr",
                    presentation_label="Kaynak 2",
                ),
            ],
            research_summary=f"Hedef kitle ({audience}), karmaşa yerine {subject} ile elde edeceği somut faydaya odaklanıyor. En başarılı formatlar doğrudan kanca ve hızlı çözüm kontrastını kullanıyor.",
        )

    return ResearchPack(
        search_id=search_id,
        audience_tensions=[
            f"{audience} struggles with inefficient alternatives and seeks a proven, reliable solution. [E1]",
            f"Clear value from {subject} cuts through market noise and saves valuable time. [E2]",
            f"Direct proof that supports {goal.lower()} drives highest engagement and trust. [E1]",
        ],
        desired_outcomes=[
            f"Achieve {goal.lower()} with {subject}.".replace("..", "."),
            f"Reliable, high-impact results tailored for {audience}.",
        ],
        format_patterns=[
            "POV + fast contrast + direct value hook. [E2]",
            "Demonstration-first feed-native showcase. [E1]",
            "Before / After direct result comparison. [E2]",
        ],
        creative_opportunity=f"Deliver tangible proof and direct results with {subject} for {audience}. [E1] [E2]",
        evidence=[
            EvidenceItem(
                evidence_id="E1",
                type="audience_language",
                claim=f"{audience} prioritizes direct results and clear reliability.",
                excerpt=f"We need a straightforward solution that actually delivers on {goal.lower()}.".replace("..", "."),
                source_title="Market Insights & Feedback",
                source_url="https://market.insights.local/feed",
                presentation_label="Source 1",
            ),
            EvidenceItem(
                evidence_id="E2",
                type="format_pattern",
                claim="High performing reels show immediate outcome demonstration in the first 2 seconds.",
                excerpt="Ads that open with direct outcome evidence outperform generic introductions by 2.4x.",
                source_title="Social Ad Performance Study",
                source_url="https://adstudy.local/report",
                presentation_label="Source 2",
            ),
        ],
        research_summary=f"The audience ({audience}) wants direct proof and reliable outcomes. {subject} wins by leading with clear value and rapid contrast.",
    )


def get_mock_direction_set(brief: Optional[CampaignBrief] = None) -> CreativeDirectionSet:
    subject = brief.subject_name if brief and brief.subject_name else "Product"
    desc = brief.subject_description if brief and brief.subject_description else "solution"
    audience = brief.audience if brief and brief.audience else "Target Audience"
    goal = brief.goal if brief and brief.goal else "Drive adoption"
    cta = brief.cta if brief and brief.cta else (f"Hemen {subject}'ı Keşfet" if (brief and getattr(brief, 'output_language', 'en') == 'tr') else f"Get Started with {subject}")
    is_tr = brief and getattr(brief, "output_language", "en") == "tr"

    if is_tr:
        return CreativeDirectionSet(
            directions=[
                CreativeDirection(
                    direction_id="D1",
                    name="Net Değer ve Doğrudan Çözüm",
                    hook=f"{subject} ile {goal.lower()} artık çok daha kolay.".replace("..", "."),
                    core_tension=f"{audience} için doğru ve güvenilir çözüme hızla ulaşma ihtiyacı.",
                    creative_hypothesis=f"Doğrudan fayda odaklı kanca {audience} kitlesinde anında güven oluşturur.",
                    visual_idea=f"{subject} ({desc}) kullanımını ve sunduğu somut avantajı öne çıkaran net çekim.",
                    cta_treatment=cta,
                    evidence_ids=["E1", "E2"],
                    why_test="E1 ve E2'deki somut fayda ve doğrudan kanca içgörüsüyle tam uyumlu.",
                    director_score=0.98,
                ),
                CreativeDirection(
                    direction_id="D2",
                    name="Öncesi ve Sonrası Dönüşüm",
                    hook=f"{audience} neden {subject}'ı tercih ediyor?",
                    core_tension="Eski ve verimsiz yöntemlerin yarattığı zaman ve kaynak kaybı.",
                    creative_hypothesis="Sorun ve çözüm arasındaki görsel kontrast hızlı karar aldırır.",
                    visual_idea=f"Karmaşık durumdan {subject} ile elde edilen yalın ve başarılı sonuca geçiş.",
                    cta_treatment=cta,
                    evidence_ids=["E2"],
                    why_test="Kanıtlanmış karşılaştırma formatıyla yüksek dönüşüm hedefler.",
                    director_score=0.88,
                ),
                CreativeDirection(
                    direction_id="D3",
                    name="Hızlı Başlangıç ve Somut Sonuç",
                    hook=f"{subject} ile tanışın, farkı hemen yaşayın.",
                    core_tension=f"{goal} yolunda pratik ve güçlü bir adım atma isteği.",
                    creative_hypothesis="Merak ve net avantaj birleşimi izlenme ve etkileşimi artırır.",
                    visual_idea=f"{subject} deneyimini ve kaliteli sonucunu sergileyen dinamik sunum.",
                    cta_treatment=cta,
                    evidence_ids=["E1"],
                    why_test="E1'deki güvenilir ve pratik deneyim talebini doğrudan karşılar.",
                    director_score=0.78,
                ),
            ],
            director_pick_direction_id="D1",
            director_pick_reason=f"'Net Değer ve Doğrudan Çözüm' yönelimi {subject} için en güçlü kancayı kuruyor ve {audience} beklentisini doğrudan karşılıyor.",
        )

    return CreativeDirectionSet(
        directions=[
            CreativeDirection(
                direction_id="D1",
                name="Direct Proof & Value",
                hook=f"Meet {subject}. Built for {audience}.",
                core_tension=f"The challenge {audience} faces in finding a dependable solution.",
                creative_hypothesis=f"Direct outcome presentation stops the scroll and builds trust with {audience}.",
                visual_idea=f"Dynamic presentation highlighting the tangible advantage of {subject} ({desc}).",
                cta_treatment=cta,
                evidence_ids=["E1", "E2"],
                why_test="Directly addresses the exact audience demand found in the research.",
                director_score=0.98,
            ),
            CreativeDirection(
                direction_id="D2",
                name="Before vs After Transformation",
                hook=f"Why {audience} is switching to {subject}.",
                core_tension="Friction and inefficiency caused by outdated alternatives.",
                creative_hypothesis="Visual contrast between the problem and the resolution inspires action.",
                visual_idea=f"High-contrast transition from frustration to clear resolution with {subject}.",
                cta_treatment=cta,
                evidence_ids=["E2"],
                why_test="Uses the proven problem-to-solution contrast format.",
                director_score=0.85,
            ),
            CreativeDirection(
                direction_id="D3",
                name="Fast Action & Results",
                hook=f"Experience the difference with {subject}.",
                core_tension=f"The search for a reliable way to {goal.lower()}.".replace("..", "."),
                creative_hypothesis="Clear product payoff drives immediate user adoption.",
                visual_idea=f"Close-up demonstration highlighting ease of use and tangible payoff of {subject}.",
                cta_treatment=cta,
                evidence_ids=["E1"],
                why_test="Delivers on the core outcome promise requested by users.",
                director_score=0.75,
            ),
        ],
        director_pick_direction_id="D1",
        director_pick_reason=f"The 'Direct Proof & Value' direction perfectly aligns with the strongest outcome tension in E1 for {subject}.",
    )


def get_mock_shot_plan(direction_id: str = "D1", brief: Optional[CampaignBrief] = None) -> ShotPlan:
    subject = brief.subject_name if brief and brief.subject_name else "Product"
    desc = brief.subject_description if brief and brief.subject_description else "solution and service"
    audience = brief.audience if brief and brief.audience else "Target Audience"
    goal = brief.goal if brief and brief.goal else "Drive adoption"
    cta = brief.cta if brief and brief.cta else (f"Hemen {subject}'ı Keşfet" if (brief and getattr(brief, 'output_language', 'en') == 'tr') else f"Get Started with {subject}")
    is_tr = brief and getattr(brief, "output_language", "en") == "tr"

    if is_tr:
        return ShotPlan(
            direction_id=direction_id,
            aspect_ratio="9:16",
            total_target_seconds=18,
            shots=[
                Shot(
                    shot_id="H1",
                    order=1,
                    duration_seconds=6,
                    purpose="hero",
                    creative_mode="relatable_scenario",
                    visual=f"{audience} için günlük hayatta yaşanan bir ihtiyaç anı ve {subject} ile gelen çözüm.",
                    action=f"Kullanıcı {subject} ile aradığı çözüme ulaşır ve rahatlar.",
                    camera="Yumuşak ve doğal el kamerası açısı.",
                    audio_direction="Belirsizlik tonundan ferah ve güven veren ses atmosferine geçiş.",
                    veo_audio_prompt="An ambient lifestyle room acoustic with a clear resolving tone and confident breath",
                    caption=f"{subject} ile {goal.lower()}.".replace("..", "."),
                    product_overlay=False,
                    veo_prompt_intent=f"Handheld medium close-up, authentic lifestyle realism presenting {subject} ({desc}), clean directional lighting and natural texture",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                    status="planned",
                ),
                Shot(
                    shot_id="H2",
                    order=2,
                    duration_seconds=6,
                    purpose="hero",
                    creative_mode="creator_demo",
                    visual=f"{subject} deneyiminin pratik ve odaklı tanıtımı.",
                    action=f"{subject} ile istenen sonuca zahmetsizce ulaşılır.",
                    camera="Yukarıdan aşağıya (top-down POV) net ve odaklı çekim.",
                    audio_direction="Temiz ve net dokunma sesleri eşliğinde dinamik fon müziği.",
                    veo_audio_prompt="Crisp modern audio cues with subtle rhythmic acoustic backing",
                    caption=f"{subject} ile kolay ve etkili sonuç.",
                    product_overlay=True,
                    veo_prompt_intent=f"Top-down POV shot, crisp demonstration of {subject} ({desc}), stable composition and feed-native commercial clarity",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                    status="planned",
                ),
                Shot(
                    shot_id="H3",
                    order=3,
                    duration_seconds=6,
                    purpose="hero",
                    creative_mode="premium_metaphor",
                    visual=f"{subject} ile elde edilen başarının ve güvenin premium yansıması.",
                    action=f"Kullanıcı memnuniyetle sonuca odaklanır.",
                    camera="Yavaşça geriye doğru süzülen sinematik kamera hareketi.",
                    audio_direction="Yükselen pozitif akorlar ve tatmin edici kapanış tonu.",
                    veo_audio_prompt="Warm uplifting chords resolving in a clean commercial payoff",
                    caption=f"{cta}.",
                    product_overlay=False,
                    veo_prompt_intent=f"Controlled macro-to-medium dolly out, premium commercial presentation of {subject} ({desc}), warm lighting and aspirational finish",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                    status="planned",
                ),
            ],
            full_reel_shots=[
                Shot(
                    shot_id="F1",
                    order=1,
                    duration_seconds=6,
                    purpose="hook",
                    creative_mode="sequential",
                    visual=f"{audience} için yaşanan temel problem ve çözüm arayışı.",
                    action="Kullanıcı duruma odaklanır ve çözüm arar.",
                    camera="Hızlı ve dikkat çekici yaklaşma hareketi.",
                    audio_direction="Merak uyandıran açılış sesi ve net geçiş.",
                    veo_audio_prompt="Subtle tension audio cue resolving quickly into a clear opening hook",
                    caption=f"{subject} ile değişimi başlatın.",
                    product_overlay=False,
                    veo_prompt_intent=f"Fast handheld push-in, relatable authentic scenario representing {subject} ({desc}), high visual clarity",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                ),
                Shot(
                    shot_id="F2",
                    order=2,
                    duration_seconds=6,
                    purpose="body",
                    creative_mode="sequential",
                    visual=f"{subject} ile somut deneyim ve fayda sunulur.",
                    action=f"{subject} devreye girer ve farkı hissettirir.",
                    camera="Sabit yakın çekim ve detay odaklı kadraj.",
                    audio_direction="Ritmik ve güven veren fon melodisi.",
                    veo_audio_prompt="Steady confident rhythm and clean natural room acoustic",
                    caption=f"{goal}.".replace("..", "."),
                    product_overlay=True,
                    veo_prompt_intent=f"Locked medium close-up, tactile demonstration of {subject} ({desc}), clean bright commercial lighting",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                ),
                Shot(
                    shot_id="F3",
                    order=3,
                    duration_seconds=6,
                    purpose="payoff",
                    creative_mode="sequential",
                    visual=f"{subject} ile hedefine ulaşan tatmin edici ve güvenli sonuç.",
                    action="Kullanıcı güven ve memnuniyetle tamamlar.",
                    camera="Akıcı ve geniş açıya açılan sinematik hareket.",
                    audio_direction="Güçlü ve olumlu kapanış akoru.",
                    veo_audio_prompt="Uplifting resolved musical tone with subtle ambient warmth",
                    caption=f"{cta}.",
                    product_overlay=False,
                    veo_prompt_intent=f"Smooth tracking shot, aspirational payoff scene highlighting the success of {subject}, credible commercial realism",
                    negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                ),
            ],
        )

    return ShotPlan(
        direction_id=direction_id,
        aspect_ratio="9:16",
        total_target_seconds=18,
        shots=[
            Shot(
                shot_id="H1",
                order=1,
                duration_seconds=6,
                purpose="hero",
                creative_mode="relatable_scenario",
                visual=f"A relatable situation for {audience} resolving with {subject}.",
                action=f"The user reaches for {subject} and finds an immediate solution.",
                camera="Feed-native handheld push-in that settles naturally.",
                audio_direction="Subtle tension resolving into clean, calm room ambience.",
                veo_audio_prompt="Subtle ambient tone resolving into a clean confident room acoustic",
                caption=f"{subject}: Built for {audience}.",
                product_overlay=False,
                veo_prompt_intent=f"Handheld medium close-up, authentic lifestyle realism highlighting {subject} ({desc}), clean directional lighting and natural texture",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                status="planned",
            ),
            Shot(
                shot_id="H2",
                order=2,
                duration_seconds=6,
                purpose="hero",
                creative_mode="creator_demo",
                visual=f"A creator demonstrates the core capability of {subject}.",
                action=f"Demonstrating how {subject} works seamlessly in practice.",
                camera="Top-down POV with crisp commercial clarity.",
                audio_direction="Tactile product cues and crisp modern backing tone.",
                veo_audio_prompt="Crisp tactile audio cues with subtle modern backing ambience",
                caption=f"Simple, powerful results with {subject}.",
                product_overlay=True,
                veo_prompt_intent=f"Top-down POV shot, crisp demonstration of {subject} ({desc}), feed-native commercial energy and natural lighting",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                status="planned",
            ),
            Shot(
                shot_id="H3",
                order=3,
                duration_seconds=6,
                purpose="hero",
                creative_mode="premium_metaphor",
                visual=f"Premium visual presentation of {subject} delivering its core promise.",
                action=f"The user experiences the outcome with confidence.",
                camera="Controlled macro-to-medium dolly out.",
                audio_direction="Layered subtle tones resolving into one clean commercial pulse.",
                veo_audio_prompt="Layered subtle acoustic cues resolving into a clean commercial payoff",
                caption=f"{cta}.",
                product_overlay=False,
                veo_prompt_intent=f"Controlled macro-to-medium dolly out, premium commercial presentation of {subject} ({desc}), warm directional light and aspirational finish",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
                status="planned",
            ),
        ],
        full_reel_shots=[
            Shot(
                shot_id="F1",
                order=1,
                duration_seconds=6,
                purpose="hook",
                creative_mode="sequential",
                visual=f"{audience} faces the common challenge before discovering {subject}.",
                action="The subject encounters the friction and looks for a better way.",
                camera="Fast handheld push-in.",
                audio_direction="Tense ambient rhythm resolving to a sharp opening hook.",
                veo_audio_prompt="Subtle tension audio cue resolving into an attention-grabbing opening",
                caption=f"There is a better way with {subject}.",
                product_overlay=False,
                veo_prompt_intent=f"Fast handheld push-in, relatable scenario for {audience} exploring {subject} ({desc}), authentic commercial realism",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
            ),
            Shot(
                shot_id="F2",
                order=2,
                duration_seconds=6,
                purpose="body",
                creative_mode="sequential",
                visual=f"{subject} is introduced and delivers its core promise.",
                action=f"The user interacts with {subject} and the outcome becomes clear.",
                camera="Locked close-up with a subtle push.",
                audio_direction="Steady confident rhythm and clean natural soundscape.",
                veo_audio_prompt="Steady confident rhythm and clean natural soundscape",
                caption=f"{goal}.".replace("..", "."),
                product_overlay=True,
                veo_prompt_intent=f"Locked medium close-up, tactile demonstration of {subject} ({desc}), clean daylight and commercial clarity",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
            ),
            Shot(
                shot_id="F3",
                order=3,
                duration_seconds=6,
                purpose="payoff",
                creative_mode="sequential",
                visual=f"The tangible outcome is achieved with calm confidence using {subject}.",
                action="The user enjoys the finished result.",
                camera="Smooth lateral tracking shot.",
                audio_direction="A resolved breath and warm uplifting commercial payoff.",
                veo_audio_prompt="A relieved breath and warm uplifting commercial payoff",
                caption=f"{cta}.",
                product_overlay=False,
                veo_prompt_intent=f"Smooth lateral tracking shot, aspirational payoff scene highlighting the success of {subject}, credible commercial finish",
                negative_constraints=["legible text", "watermarks", "brand logos", "distorted screens", "malformed hands"],
            ),
        ],
    )
