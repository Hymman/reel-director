import re
from typing import Optional, Literal
from app.models.campaign import CampaignBrief


class EvaluateBriefResult:
    def __init__(self, is_sufficient: bool, clarification_question: Optional[str] = None):
        self.is_sufficient = is_sufficient
        self.clarification_question = clarification_question


def detect_language(text: str) -> str:
    """Detect if the prompt is Turkish or English, supporting both UTF-8 and ASCII Turkish."""
    lower = text.lower()
    # Turkish characters
    tr_chars = set("çğıöşüÇĞIİÖŞÜ")
    if any(c in tr_chars for c in text):
        return "tr"
    # Common Turkish advertising/brief keywords (both UTF-8 and ASCII variants)
    tr_keywords = [
        "türkçe", "turkce", "için", "icin", "hedef", "kitle", "kitlemiz", "kitlesi",
        "amaç", "amac", "amacımız", "amacimiz", "amacı", "amaci", "reklam", "dili",
        "ebeveyn", "ebeveynler", "çocuk", "cocuk", "çocuklar", "cocuklar",
        "deneme", "denemeyi", "ücretsiz", "ucretsiz", "ücretli", "ucretli",
        "abonelik", "aboneliği", "aboneligi", "uygulama", "uygulaması", "uygulamasi",
        "masal", "masallar", "nakit", "akışı", "akisi", "takibi", "yapan", "sunan",
        "olan", "bir", "başlatmak", "baslatmak", "artırmak", "artirmak",
        "kolay", "hızlı", "hizli", "kobi", "işletmeler", "isletmeler", "küçük", "kucuk",
        "sakinleştirici", "sakinlestirici", "eğitici", "egitici", "sıcak", "sicak", "güven", "guven"
    ]
    words = set(re.findall(r"\b\w+\b", lower))
    if any(kw in words for kw in tr_keywords):
        return "tr"
    return "en"


def evaluate_demo_brief(raw_text: str) -> EvaluateBriefResult:
    """Check if the brief is sufficient or needs 1 conversational clarification."""
    cleaned = clean_raw_input(raw_text)
    words = cleaned.split()
    if len(words) < 4:
        lang = detect_language(raw_text)
        if lang == "tr":
            return EvaluateBriefResult(
                is_sufficient=False,
                clarification_question="Uygulamanız veya ürününüz tam olarak ne işe yarıyor ve hedef kitleniz kim?"
            )
        else:
            return EvaluateBriefResult(
                is_sufficient=False,
                clarification_question="Could you tell me a bit more about what your product does and who it is for?"
            )
    return EvaluateBriefResult(is_sufficient=True, clarification_question=None)


def clean_raw_input(raw_text: str) -> str:
    """Strip wrapper tags and prefixes like 'Original Request:', 'Clarification Answer:'."""
    lines = []
    for line in raw_text.splitlines():
        # Remove wrapper headers
        cleaned = re.sub(
            r"^(?:original request|clarification answer|reference context|user brief|prompt|kullanıcı briefi|yanıt)\s*[:\-]\s*",
            "",
            line,
            flags=re.IGNORECASE
        ).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def extract_demo_brief(raw_text: str, context_summary: Optional[str] = None, original_brief: Optional[str] = None, answer: Optional[str] = None) -> CampaignBrief:
    """Deterministically parse and infer structured brief fields from user input."""
    cleaned_input = clean_raw_input(raw_text)
    if original_brief and answer:
        # Combined cleanly without wrapper headers
        clean_text = f"{clean_raw_input(original_brief)}\n{clean_raw_input(answer)}"
    else:
        clean_text = cleaned_input

    lang = detect_language(clean_text)

    # 1. Subject Name Extraction
    subject_name = ""
    first_meaningful_line = clean_text.split("\n")[0].strip() if clean_text else ""
    if original_brief:
        first_meaningful_line = clean_raw_input(original_brief).split("\n")[0].strip()

    # Check for explicit prefixes like 'Ürün: ...', 'Subject: ...', 'Brand: ...'
    prefix_match = re.match(
        r"^(?:subject|product|brand|ürün|urun|marka|konu|proje)\s*[:\-]\s*([^,\n.]+)",
        first_meaningful_line,
        re.IGNORECASE
    )
    if prefix_match:
        subject_name = prefix_match.group(1).strip()
    else:
        # Check first clause before comma / dash / colon / 'is a' / 'bir'
        split_match = re.split(
            r"[,:\-\–\—]|\s+(?:is a|is an|bir|adlı|adli|adında|adinda)\s+",
            first_meaningful_line,
            maxsplit=1,
            flags=re.IGNORECASE
        )
        if split_match and split_match[0].strip():
            candidate = split_match[0].strip()
            # Clean out polite introductory words
            candidate = re.sub(r"^(?:lütfen|lutfen|please|yeni bir|new)\s+", "", candidate, flags=re.IGNORECASE).strip()
            if candidate and len(candidate.split()) <= 4:
                subject_name = candidate

    if not subject_name:
        words = first_meaningful_line.split()
        subject_name = " ".join(words[:2]).rstrip(",.:-") if words else ("Proje" if lang == "tr" else "Project")

    # Clean punctuation and wrapper leaks
    subject_name = re.sub(r"^(?:original request|clarification answer|reference context)\s*", "", subject_name, flags=re.IGNORECASE).strip()
    if not subject_name:
        subject_name = "Proje" if lang == "tr" else "Project"

    if subject_name.islower():
        subject_name = subject_name.title()

    # 2. Target Audience Extraction
    audience = ""
    aud_patterns = [
        r"(?:hedef kitle|hedef kitlemiz|hedef kitlesi|hedef kitlem|hedef)\s*[:\-]?\s*([^.,;\n]+)",
        r"(?:target audience|audience|target)\s*[:\-]?\s*([^.,;\n]+)",
        r"([\w\s\-çğıöşüÇĞIİÖŞÜ]+)\s+(?:için|icin)\s+(?:tasarlanmış|tasarlanmis|geliştirilmiş|gelistirilmis|sunulan|yapan|olan|bir)",
        r"(?:for|aimed at|designed for)\s+([\w\s\-]+?)(?=\.|\,|;|$|\s+(?:to|who|and))",
    ]
    for pattern in aud_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            extracted_aud = match.group(1).strip()
            # Filter out non-audience words
            if len(extracted_aud.split()) <= 8 and not re.search(r"^(?:ve|and|ile|amaç|amac|goal)$", extracted_aud, re.IGNORECASE):
                audience = extracted_aud.rstrip(",.;")
                break

    if not audience:
        audience = "Kullanıcılar ve işletmeler" if lang == "tr" else "General audience and users"

    if audience:
        audience = audience[0].upper() + audience[1:]

    # 3. Goal Extraction
    goal = ""
    goal_patterns = [
        r"(?:amaç|amac|amacımız|amacimiz|amacı|amaci|hedefimiz|hedefim|kampanya hedefi)\s*[:\-]?\s*([^.,;\n]+)",
        r"(?:goal|purpose|objective|aim|campaign goal)\s*[:\-]?\s*([^.,;\n]+)",
        r"\bhedef\b(?!\s+kitle)\s*[:\-]?\s*([^.,;\n]+)",
    ]
    for pattern in goal_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            extracted_goal = match.group(1).strip()
            if len(extracted_goal.split()) <= 10:
                goal = extracted_goal.rstrip(",.;")
                break

    if not goal:
        if re.search(r"(?:ücretli|ucretli|satış|satis|abonelik|satın al|satin al|sipariş|siparis)", clean_text, re.IGNORECASE):
            goal = "Ücretli abonelik başlatmak ve satışları artırmak" if lang == "tr" else "Drive paid conversions and sales"
        elif re.search(r"(?:deneme|ücretsiz|ucretsiz|kayıt|kayit|indirme|tanıtım|tanitim)", clean_text, re.IGNORECASE):
            goal = "Ücretsiz denemeyi başlatmak ve kullanıcı kazanmak" if lang == "tr" else "Drive free trials and app installs"
        elif re.search(r"(?:purchase|order|buy|subscription|sales|pre-order)", clean_text, re.IGNORECASE):
            goal = "Drive online purchases and customer conversion"
        elif re.search(r"(?:trial|free|install|download|sign up)", clean_text, re.IGNORECASE):
            goal = "Drive free trials and user adoption"
        else:
            goal = "Marka bilinirliği ve dönüşüm sağlamak" if lang == "tr" else "Drive brand awareness and product adoption"

    if goal:
        goal = goal[0].upper() + goal[1:]

    # 4. Subject Description
    # Remove metadata lines (Hedef kitle, Amaç, Reklam dili, etc.) from description
    cleaned_desc_lines = []
    for line in clean_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if re.search(r"^(?:hedef kitle|amaç|amac|reklam dili|target audience|goal|campaign language)\s*[:\-]", line_clean, re.IGNORECASE):
            continue
        cleaned_desc_lines.append(line_clean)

    desc_text = " ".join(cleaned_desc_lines) if cleaned_desc_lines else clean_text
    sentences = [s.strip() for s in re.split(r"[.\n;]+", desc_text) if s.strip()]
    if sentences:
        description = sentences[0]
        if len(sentences) > 1 and len(description.split()) < 8:
            description = f"{sentences[0]}. {sentences[1]}"
    else:
        description = desc_text

    # 5. Call To Action (CTA)
    cta = ""
    if lang == "tr":
        if re.search(r"(?:ücretli|ucretli|abone|satın|satin|başlat|baslat)", clean_text, re.IGNORECASE) and not re.search(r"(?:ücretsiz|ucretsiz)", clean_text, re.IGNORECASE):
            cta = f"Hemen {subject_name}'a Katılın"
        elif re.search(r"(?:ücretsiz|ucretsiz|deneme)", clean_text, re.IGNORECASE):
            cta = "Hemen Ücretsiz Dene"
        elif re.search(r"(?:indir|mobil|uygulama)", clean_text, re.IGNORECASE):
            cta = "Hemen İndir"
        else:
            cta = f"{subject_name}'ı Keşfet"
    else:
        if re.search(r"(?:purchase|buy|order|shop|pre-order)", clean_text, re.IGNORECASE):
            cta = f"Shop {subject_name} Now"
        elif re.search(r"(?:free|trial)", clean_text, re.IGNORECASE):
            cta = f"Try {subject_name} Free"
        elif re.search(r"(?:download|app)", clean_text, re.IGNORECASE):
            cta = f"Download {subject_name}"
        else:
            cta = f"Get Started with {subject_name}"

    # 6. Intent Type
    intent_type: Literal["promotion", "topic"] = "promotion"

    return CampaignBrief(
        raw_text=raw_text,
        subject_name=subject_name,
        subject_description=description,
        audience=audience,
        goal=goal,
        cta=cta,
        intent_type=intent_type,
        output_language=lang,
    )
