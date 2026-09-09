from types import SimpleNamespace

from app.models.campaign import CampaignBrief
from app.services.parallel_service import curate_search_results


def _result(title: str, url: str, excerpts=None, publish_date=None):
    return SimpleNamespace(
        title=title,
        url=url,
        excerpts=excerpts or [],
        publish_date=publish_date,
    )


def _brief() -> CampaignBrief:
    return CampaignBrief(
        subject_name="DreamLetter",
        subject_description="Rüyaları hızlıca kaydeden kişisel bir rüya günlüğü",
        audience="Rüyalarını unutmadan kaydetmek isteyen yetişkinler",
        output_language="tr",
    )


def test_curates_parallel_excerpts_and_rejects_noise():
    results = [
        (
            0,
            [
                _result(
                    "DreamLetter: dream journal",
                    "https://play.google.com/store/apps/details?id=com.lubaworks.dreamletter&utm_source=test",
                    ["DreamLetter helps people record a dream quickly and revisit their personal journal over time."],
                    "2026-08-20",
                ),
                _result(
                    "Dreamletter APK download",
                    "https://apkcombo.com/dreamletter-ai-dream-journal/com.lubaworks.dreamletter",
                    ["Download the DreamLetter APK package from this mirror website."],
                ),
                _result(
                    "Dreame - Romantic Stories",
                    "https://play.google.com/store/apps/details?id=com.dreame.reader",
                    ["Read serialized romance stories and fictional novels from popular authors."],
                ),
                _result(
                    "Why keep a dream journal?",
                    "https://example.org/guides/dream-journal",
                    ["A dream journal can help a person preserve details that often fade soon after waking."],
                ),
                _result(
                    "Metadata only result",
                    "https://example.net/empty",
                    [],
                ),
                _result(
                    "Mobil uygulama hedef kitle rehberi",
                    "https://example.net/generic-app-marketing",
                    ["Mobil uygulamalar için hedef kitle ve pazarlama stratejisi oluşturma rehberi."],
                ),
            ],
        ),
        (
            1,
            [
                _result(
                    "Duplicate DreamLetter listing",
                    "https://play.google.com/store/apps/details?id=com.lubaworks.dreamletter&hl=tr",
                    ["DreamLetter helps people record a dream quickly and revisit their personal journal over time."],
                )
            ],
        ),
    ]

    evidence = curate_search_results(
        results,
        _brief(),
        ["rüya kaydetme uygulaması", "DreamLetter rakipleri"],
    )

    assert [item.evidence_id for item in evidence] == [f"E{i}" for i in range(1, len(evidence) + 1)]
    assert len(evidence) == 2
    assert all(item.excerpt for item in evidence)
    assert all("metadata" not in item.claim.lower() for item in evidence)
    assert all("apkcombo.com" not in item.source_url for item in evidence)
    assert all("dreame.reader" not in item.source_url for item in evidence)
    assert all("generic-app-marketing" not in item.source_url for item in evidence)
    assert evidence[0].published_at == "2026-08-20"


def test_metadata_only_results_are_not_treated_as_evidence():
    evidence = curate_search_results(
        [(0, [_result("DreamLetter listing", "https://example.com/dreamletter", [])])],
        _brief(),
        ["DreamLetter rüya günlüğü"],
    )

    assert evidence == []
