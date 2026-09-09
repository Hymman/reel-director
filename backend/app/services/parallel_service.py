import os
import time
import asyncio
import re
from collections import defaultdict
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from parallel import AsyncParallel
import traceback

from app.config import settings
from app.models.campaign import CampaignBrief, EvidenceItem, ResearchPack


_BLOCKED_SOURCE_DOMAINS = {
    "apkcombo.com",
    "apkpure.com",
    "apkmonk.com",
    "uptodown.com",
}

_GENERIC_TERMS = {
    "about", "after", "again", "against", "android", "app", "application",
    "best", "campaign", "content", "create", "creative", "different",
    "designed", "etkili", "farkli", "hedef", "icin", "instagram", "karsi",
    "kişisel", "kitle", "kullanici", "kullanıcı",
    "market", "marketing", "mevcut", "mobile", "nasil", "nelerdir", "olan",
    "olarak", "platform", "reels", "social", "strateji", "target", "video",
    "what", "which", "with", "uygulama", "uygulamalar", "pazarlama", "tasarlanmış",
}


def _tokens(value: str) -> set[str]:
    # Splitting CamelCase keeps brand names such as DreamLetter useful for
    # relevance checks while preserving Turkish words and diacritics.
    expanded = re.sub(r"([a-z])([A-Z])", r"\1 \2", value or "")
    return {
        token
        for token in re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", expanded.lower())
        if len(token) >= 4 and token not in _GENERIC_TERMS
    }


def _canonical_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if not host:
            return ""
        path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
        stable_query = urlencode(sorted(
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=False)
            if not key.lower().startswith("utm_") and key.lower() not in {"hl", "gl", "ref", "source"}
        ))
        return urlunsplit((parsed.scheme.lower() or "https", host, path, stable_query, ""))
    except ValueError:
        return ""


def _source_host(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _blocked_source(value: str) -> bool:
    host = _source_host(value)
    return any(host == domain or host.endswith(f".{domain}") for domain in _BLOCKED_SOURCE_DOMAINS)


def _clean_excerpt(item: Any) -> str:
    # Parallel WebSearchResult exposes `excerpts`; content/snippet are retained
    # only for compatibility with older fixtures and provider response shapes.
    excerpts = getattr(item, "excerpts", None) or []
    if isinstance(excerpts, str):
        excerpts = [excerpts]
    content = " ".join(str(part).strip() for part in excerpts if str(part).strip())
    if not content:
        content = str(getattr(item, "content", "") or getattr(item, "snippet", "") or "").strip()
    return re.sub(r"\s+", " ", content).strip()[:700]


def _stem_term(value: str) -> str:
    # Conservative suffix stripping avoids treating similarly named products
    # (Dream vs. Dreame) as a semantic match.
    suffixes = (
        "larını", "lerini", "ları", "leri", "lardan", "lerden", "lar", "ler",
        "ının", "inin", "unun", "ünün", "ını", "ini", "unu", "ünü",
        "dan", "den", "ing", "ed", "es", "s",
    )
    for suffix in suffixes:
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            return value[:-len(suffix)]
    return value


def _term_hits(left: set[str], right: set[str]) -> set[str]:
    """Match conservative inflections such as rüya/rüyaları and dream/dreams."""
    return {
        term
        for term in left
        if any(term == other or _stem_term(term) == _stem_term(other) for other in right)
    }


def _relevance_score(item: Any, brief: CampaignBrief, query: str, excerpt: str) -> int:
    title = str(getattr(item, "title", "") or "")
    url = str(getattr(item, "url", "") or "")
    subject_terms = _tokens(f"{brief.subject_name} {brief.subject_description}")
    query_terms = _tokens(query)
    title_terms = _tokens(f"{title} {url}")
    excerpt_terms = _tokens(excerpt)

    subject_title_hits = _term_hits(subject_terms, title_terms)
    subject_body_hits = _term_hits(subject_terms, excerpt_terms)
    query_hits = _term_hits(query_terms, title_terms | excerpt_terms)
    # A campaign evidence source must be about the actual subject. Generic app
    # marketing/target-audience pages can inform a writer, but they cannot ground
    # claims or directions for this product/category.
    if not (subject_title_hits or subject_body_hits):
        return 0

    score = (len(subject_title_hits) * 3) + len(subject_body_hits) + len(query_hits)
    if _source_host(url) in {"play.google.com", "apps.apple.com"}:
        score += 1
    return score


def curate_search_results(
    result_groups: list[tuple[int, list[Any]]],
    brief: CampaignBrief,
    search_queries: list[str],
    max_items: int = 15,
) -> list[EvidenceItem]:
    """Return excerpt-backed, relevant, de-duplicated evidence.

    This deliberately fails closed: metadata-only results are not evidence and
    package mirrors are not suitable sources for customer-facing claim support.
    """
    candidates: list[tuple[int, int, str, str, str, Any]] = []
    seen_urls: set[str] = set()

    for query_idx, query_results in result_groups:
        query = search_queries[query_idx] if query_idx < len(search_queries) else ""
        for item in query_results[:5]:
            url = str(getattr(item, "url", "") or "")
            canonical = _canonical_url(url)
            excerpt = _clean_excerpt(item)
            if not canonical or canonical in seen_urls or _blocked_source(url) or len(excerpt) < 40:
                continue
            score = _relevance_score(item, brief, query, excerpt)
            if score < 3:
                continue
            seen_urls.add(canonical)
            title = str(getattr(item, "title", "") or _source_host(url) or "Web Source")
            candidates.append((score, query_idx, canonical, title, excerpt, item))

    candidates.sort(key=lambda row: (-row[0], row[1], row[3].lower()))
    domain_counts: dict[str, int] = defaultdict(int)
    evidence: list[EvidenceItem] = []
    for _, query_idx, canonical, title, excerpt, item in candidates:
        host = _source_host(canonical)
        if domain_counts[host] >= 2:
            continue
        domain_counts[host] += 1
        first_sentence = re.split(r"(?<=[.!?])\s+", excerpt, maxsplit=1)[0]
        claim = first_sentence[:240].rstrip()
        evidence.append(
            EvidenceItem(
                evidence_id=f"E{len(evidence) + 1}",
                type="category_observation",
                claim=claim,
                excerpt=excerpt,
                source_title=title,
                source_url=canonical,
                published_at=getattr(item, "publish_date", None),
                presentation_label=f"Research question {query_idx + 1}",
            )
        )
        if len(evidence) >= max_items:
            break
    return evidence

class ParallelService:
    def __init__(self):
        self.api_key = settings.parallel_api_key
        if not self.api_key:
            print("WARNING: PARALLEL_API_KEY is not set. Parallel Search will fail in live mode.")

    async def execute_research(self, brief: CampaignBrief, plan: Any) -> ResearchPack:
        start_time = time.time()
        
        # Parallel Search Queries dynamically driven by AI Research Plan (Fix 2)
        search_queries = plan.research_questions if plan and plan.research_questions else [
            f"common frustrations and challenges for {brief.audience} regarding {brief.subject_description}",
            f"best performing short-form video ad formats for {brief.subject_description} targeting {brief.audience}"
        ]

        try:
            results: list[tuple[int, list[Any]]] = []
            client = AsyncParallel(api_key=self.api_key)
            
            # Run the parallel queries concurrently
            tasks = []
            for query in search_queries:
                tasks.append(client.search(
                    objective=(
                        f"Find directly relevant, credible evidence for {brief.subject_name}: "
                        f"{brief.subject_description}. The campaign targets {brief.audience}. "
                        "Exclude similarly named but unrelated products and low-quality download mirrors."
                    ),
                    search_queries=[query],
                    max_chars_total=3500,
                ))
            
            search_responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for query_idx, resp in enumerate(search_responses):
                if not isinstance(resp, Exception):
                    results.append((query_idx, list(getattr(resp, "results", []))))
            
            evidence_items = curate_search_results(results, brief, search_queries)
            if not evidence_items:
                raise ValueError("Parallel returned no excerpt-backed, relevant evidence. Refine the brief and retry.")
            
            latency = time.time() - start_time
            
            return ResearchPack(
                search_id=f"search_{os.urandom(8).hex()}",
                query_count=len(search_queries),
                evidence=evidence_items,
                research_summary=f"Live research complete with {len(evidence_items)} curated sources.",
                latency_seconds=latency
            )

        except Exception as e:
            traceback.print_exc()
            raise Exception(f"Parallel Search API failed: {str(e)}")

parallel_service = ParallelService()
