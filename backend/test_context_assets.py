import io
import os
import tempfile
import zipfile
from collections import namedtuple
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.campaign import Campaign, CampaignBrief
from app.models.job import Job
from app.models.library import AssetRecord, BrandKit, BrandProfileProposal
from app.services.context_service import ContextService
from app.services.state_store import JsonFileStore
import app.routers.assets as assets_router
import app.routers.brand_kit as brand_router
import app.routers.campaigns as campaigns_router
import app.routers.jobs as jobs_router


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_library(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        asset_store = JsonFileStore(os.path.join(tmpdir, "assets.json"), AssetRecord)
        kit_store = JsonFileStore(os.path.join(tmpdir, "brand_kits.json"), BrandKit)
        campaign_store = JsonFileStore(os.path.join(tmpdir, "campaigns.json"), Campaign)
        job_store = JsonFileStore(os.path.join(tmpdir, "jobs.json"), Job)
        private_dir = os.path.join(tmpdir, "private")

        monkeypatch.setattr(assets_router, "asset_store", asset_store)
        monkeypatch.setattr(assets_router, "workspace_storage_dir", lambda workspace_id: os.path.join(private_dir, workspace_id))
        monkeypatch.setattr(brand_router, "asset_store", asset_store)
        monkeypatch.setattr(brand_router, "brand_kit_store", kit_store)
        monkeypatch.setattr(campaigns_router, "asset_store", asset_store)
        monkeypatch.setattr(campaigns_router, "campaign_store", campaign_store)
        monkeypatch.setattr(campaigns_router, "job_store", job_store)
        monkeypatch.setattr(jobs_router, "job_store", job_store)

        class MockGemini:
            def __init__(self):
                self.last_extract_text = ""

            async def evaluate_brief(self, text):
                Result = namedtuple("Result", ["is_sufficient", "clarification_question"])
                if "NEEDS_CLARIFICATION" in text:
                    return Result(False, "Who is this product for?")
                return Result(True, None)

            async def extract_brief(self, text):
                self.last_extract_text = text
                return CampaignBrief(
                    subject_name="Context Product",
                    subject_description="Extracted with context",
                    audience="Creators",
                    output_language="en",
                )

            async def analyze_media_assets(self, assets):
                return "A clean mobile product interface with a green accent."

            async def suggest_brand_profile(self, kit, assets, context_text="", ui_language="en"):
                return BrandProfileProposal(
                    brand_voice="Calm, private and reassuring",
                    font_family="Georgia",
                    caption_preset="editorial",
                    cta_treatment="minimal",
                    motion_preset="subtle",
                    default_visual_treatment="campaign_mood",
                    sample_headline="Write what matters",
                    sample_caption="A private space for thoughts worth keeping.",
                    sample_cta="Start writing",
                    rationale="The product context supports an editorial, trust-led starting system.",
                )

        mock_gemini = MockGemini()
        monkeypatch.setattr(campaigns_router, "gemini_service", mock_gemini)
        monkeypatch.setattr(brand_router, "gemini_service", mock_gemini)
        monkeypatch.setattr(campaigns_router.settings, "demo_mode", False)
        yield asset_store, kit_store, campaign_store, job_store, tmpdir, mock_gemini


def test_private_upload_list_and_content_are_workspace_scoped(isolated_library):
    headers_a = {"X-Workspace-ID": "WS_A"}
    headers_b = {"X-Workspace-ID": "WS_B"}
    response = client.post(
        "/api/assets",
        headers=headers_a,
        files={"file": ("../brief.txt", b"Product promise and audience language", "text/plain")},
    )
    assert response.status_code == 200
    asset = response.json()
    assert asset["name"] == "brief.txt"
    assert asset["kind"] == "text"
    assert "Product promise" in asset["text_preview"]

    assert [item["asset_id"] for item in client.get("/api/assets", headers=headers_a).json()] == [asset["asset_id"]]
    assert client.get("/api/assets", headers=headers_b).json() == []
    assert client.get(f"/api/assets/{asset['asset_id']}/content", headers=headers_a).content == b"Product promise and audience language"
    assert client.get(f"/api/assets/{asset['asset_id']}/content", headers=headers_b).status_code == 404
    assert client.post("/api/assets", headers=headers_a, files={"file": ("bad.exe", b"x", "application/octet-stream")}).status_code == 415


def test_docx_text_extraction_uses_document_xml(tmp_path):
    docx_path = tmp_path / "brief.docx"
    document_xml = b'<?xml version="1.0"?><w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>Hello brand context</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    assert ContextService.extract_file_text(str(docx_path), "docx") == "Hello brand context"


def test_pdf_text_extraction_reads_embedded_page_text(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    pdf_path = tmp_path / "brief.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 16 Tf 72 720 Td (Hello PDF campaign context) Tj ET")
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)
    with open(pdf_path, "wb") as handle:
        writer.write(handle)

    assert "Hello PDF campaign context" in ContextService.extract_file_text(str(pdf_path), "pdf")


def test_url_import_blocks_private_hosts_and_persists_readable_context(isolated_library, monkeypatch):
    headers = {"X-Workspace-ID": "WS_URL"}
    assert client.post("/api/assets/url", headers=headers, json={"url": "http://127.0.0.1/admin"}).status_code == 400

    fetch_spy = AsyncMock(return_value="A public product page with a clear value proposition.")
    monkeypatch.setattr(assets_router.context_service, "fetch_url_text", fetch_spy)
    response = client.post("/api/assets/url", headers=headers, json={"url": "https://example.com/product", "name": "Product page"})
    assert response.status_code == 200
    assert response.json()["kind"] == "url"
    assert "value proposition" in response.json()["text_preview"]
    fetch_spy.assert_awaited_once_with("https://example.com/product")


def test_brand_kit_persists_and_rejects_cross_workspace_assets(isolated_library):
    headers_a = {"X-Workspace-ID": "WS_BRAND_A"}
    headers_b = {"X-Workspace-ID": "WS_BRAND_B"}
    logo_buffer = io.BytesIO()
    Image.new("RGB", (24, 24), "#123456").save(logo_buffer, "PNG")
    uploaded = client.post(
        "/api/assets",
        headers=headers_a,
        files={"file": ("logo.png", logo_buffer.getvalue(), "image/png")},
    ).json()
    payload = {
        "workspace_id": "ignored-client-value",
        "brand_name": "FocusFlow",
        "brand_voice": "Calm and precise",
        "logo_asset_id": uploaded["asset_id"],
        "product_asset_ids": [uploaded["asset_id"]],
        "brand_colors": ["#123456", "#ABCDEF"],
        "font_family": "Inter",
        "caption_preset": "bold",
        "cta_treatment": "card",
        "motion_preset": "subtle",
    }
    saved = client.put("/api/brand-kit", headers=headers_a, json=payload)
    assert saved.status_code == 200
    assert saved.json()["workspace_id"] == "WS_BRAND_A"
    assert client.get("/api/brand-kit", headers=headers_a).json()["brand_name"] == "FocusFlow"

    cross_workspace = client.put("/api/brand-kit", headers=headers_b, json=payload)
    assert cross_workspace.status_code == 404
    invalid_color = {**payload, "brand_colors": ["red"]}
    assert client.put("/api/brand-kit", headers=headers_a, json=invalid_color).status_code == 400


def test_brand_roles_and_local_palette_extraction_are_workspace_scoped(isolated_library):
    headers = {"X-Workspace-ID": "WS_PALETTE"}
    image = Image.new("RGB", (180, 120), "#102040")
    image.paste(Image.new("RGB", (90, 60), "#E35B2D"), (0, 0))
    image.paste(Image.new("RGB", (90, 60), "#E9C46A"), (90, 60))
    payload = io.BytesIO()
    image.save(payload, "PNG")
    uploaded = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("hero-product.png", payload.getvalue(), "image/png")},
    ).json()

    extracted = client.post(
        "/api/brand-kit/extract-palette",
        headers=headers,
        json={"asset_id": uploaded["asset_id"]},
    )
    assert extracted.status_code == 200
    colors = extracted.json()["colors"]
    assert len(colors) == 3
    assert all(len(color) == 7 and color.startswith("#") for color in colors)

    saved = client.put(
        "/api/brand-kit",
        headers=headers,
        json={
            "workspace_id": "ignored",
            "brand_name": "Palette Brand",
            "logo_asset_id": uploaded["asset_id"],
            "primary_product_asset_id": uploaded["asset_id"],
            "product_asset_ids": [uploaded["asset_id"]],
            "brand_colors": colors,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["primary_product_asset_id"] == uploaded["asset_id"]
    assert saved.json()["product_asset_ids"] == []
    assert client.post(
        "/api/brand-kit/extract-palette",
        headers={"X-Workspace-ID": "WS_OTHER"},
        json={"asset_id": uploaded["asset_id"]},
    ).status_code == 404


def test_brand_kit_rejects_high_confidence_reversed_logo_and_product_roles(isolated_library):
    headers = {"X-Workspace-ID": "WS_ROLE_GUARD"}
    screenshot_bytes = io.BytesIO()
    Image.new("RGB", (432, 768), "#102040").save(screenshot_bytes, "JPEG")
    icon_bytes = io.BytesIO()
    Image.new("RGB", (512, 512), "#203060").save(icon_bytes, "PNG")
    screenshot = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("product-detail-screen.jpg", screenshot_bytes.getvalue(), "image/jpeg")},
    ).json()
    icon = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("app-icon-512.png", icon_bytes.getvalue(), "image/png")},
    ).json()

    reversed_roles = client.put(
        "/api/brand-kit",
        headers=headers,
        json={
            "workspace_id": "ignored",
            "brand_name": "DreamLetter",
            "logo_asset_id": screenshot["asset_id"],
            "primary_product_asset_id": icon["asset_id"],
            "product_asset_ids": [],
            "brand_colors": ["#F6F0E3", "#08172B", "#C8A358"],
        },
    )
    assert reversed_roles.status_code == 400
    assert "appear swapped" in reversed_roles.json()["detail"]

    corrected_roles = client.put(
        "/api/brand-kit",
        headers=headers,
        json={
            "workspace_id": "ignored",
            "brand_name": "DreamLetter",
            "logo_asset_id": icon["asset_id"],
            "primary_product_asset_id": screenshot["asset_id"],
            "product_asset_ids": [],
            "brand_colors": ["#F6F0E3", "#08172B", "#C8A358"],
        },
    )
    assert corrected_roles.status_code == 200


def test_smart_brand_starter_uses_trusted_context_and_returns_editable_profile(isolated_library):
    headers = {"X-Workspace-ID": "WS_SMART_BRAND"}
    image = Image.new("RGB", (180, 120), "#13243A")
    image.paste(Image.new("RGB", (90, 120), "#E7B566"), (90, 0))
    payload = io.BytesIO()
    image.save(payload, "PNG")
    uploaded = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("brand.png", payload.getvalue(), "image/png")},
    ).json()
    kit = {
        "workspace_id": "ignored",
        "brand_name": "DreamLetter",
        "logo_asset_id": uploaded["asset_id"],
        "primary_product_asset_id": uploaded["asset_id"],
        "product_asset_ids": [],
        "brand_colors": ["#F5F5F0", "#111111", "#7CFFB2"],
    }
    response = client.post(
        "/api/brand-kit/suggest",
        headers=headers,
        json={"kit": kit, "ui_language": "en"},
    )
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["source"] == "gemini"
    assert suggestion["caption_preset"] == "editorial"
    assert suggestion["default_visual_treatment"] == "campaign_mood"
    assert suggestion["sample_cta"] == "Start writing"
    assert len(suggestion["brand_colors"]) == 3
    assert suggestion["context_key"].startswith("dreamletter|")

    cross_workspace = client.post(
        "/api/brand-kit/suggest",
        headers={"X-Workspace-ID": "WS_OTHER"},
        json={"kit": kit, "ui_language": "en"},
    )
    assert cross_workspace.status_code == 404


def test_smart_brand_fallback_rejects_generic_voice_and_preserves_premium_signal():
    kit = BrandKit(
        workspace_id="WS_FALLBACK",
        brand_name="DreamLetter",
        brand_voice="concise and practical",
        smart_profile_rationale="A premium, calm and privacy-aware product experience.",
    )
    proposal = brand_router._fallback_profile(kit, "en")
    assert proposal.brand_voice != "concise and practical"
    assert "privacy" in proposal.brand_voice.lower()
    assert proposal.caption_preset == "editorial"
    assert proposal.default_visual_treatment == "campaign_mood"


def test_contextual_intake_inherits_refs_and_allows_at_most_one_clarification(isolated_library, monkeypatch):
    asset_store, _, campaign_store, job_store, tmpdir, mock_gemini = isolated_library
    headers_a = {"X-Workspace-ID": "WS_CONTEXT_A"}
    headers_b = {"X-Workspace-ID": "WS_CONTEXT_B"}
    image_path = os.path.join(tmpdir, "product.png")
    with open(image_path, "wb") as handle:
        handle.write(b"fake-image")
    image = AssetRecord(workspace_id="WS_CONTEXT_A", name="product.png", kind="image", mime_type="image/png", size_bytes=10, storage_key=image_path)
    asset_store.save(image.asset_id, image)

    build_context = AsyncMock(return_value="Reference context summary")
    monkeypatch.setattr(campaigns_router.context_service, "build_context", build_context)
    response = client.post(
        "/api/campaigns/extract-brief",
        headers=headers_a,
        json={"raw_text": "Build a launch reel", "source_urls": ["https://example.com"], "asset_ids": [image.asset_id]},
    )
    assert response.status_code == 200
    campaign = campaign_store.get(response.json()["campaign_id"])
    job = job_store.get(response.json()["job_id"])
    assert campaign.workspace_id == job.workspace_id == "WS_CONTEXT_A"
    assert campaign.context_asset_ids == [image.asset_id]
    assert campaign.context_urls == ["https://example.com"]
    assert campaign.context_summary == "Reference context summary"
    assert campaign.brief.product_asset_uri == f"/api/assets/{image.asset_id}/content"
    assert "Reference context summary" in mock_gemini.last_extract_text

    assert client.post(
        "/api/campaigns/extract-brief",
        headers=headers_b,
        json={"raw_text": "Try to steal context", "asset_ids": [image.asset_id]},
    ).status_code == 404

    clarification = client.post(
        "/api/campaigns/extract-brief",
        headers=headers_a,
        json={"raw_text": "NEEDS_CLARIFICATION"},
    )
    clarified_campaign = campaign_store.get(clarification.json()["campaign_id"])
    assert clarified_campaign.stage == "intake_clarification"
    assert clarified_campaign.intake_state.clarification_count == 1
    answer = client.post(
        f"/api/campaigns/{clarified_campaign.id}/answer-clarification",
        headers=headers_a,
        json={"answer": "Independent creators"},
    )
    assert answer.status_code == 200
    assert campaign_store.get(clarified_campaign.id).stage == "brief_review"
    assert client.post(
        f"/api/campaigns/{clarified_campaign.id}/answer-clarification",
        headers=headers_a,
        json={"answer": "A second answer"},
    ).status_code == 400
