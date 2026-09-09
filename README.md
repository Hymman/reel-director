# Reel Director

> Research what is worth making. Direct it. Produce the campaign.

Reel Director is an agentic creative production studio for short-form social campaigns. A creator supplies a conversational brief and optional URLs, images, video, PDF, DOCX, TXT, or Markdown. Reel Director researches the audience and category, proposes evidence-grounded creative directions, offers three production candidates, and turns the selected direction into branded, downloadable campaign assets.

Built for the **Parallel track** of Google Cloud Agentic Cinema: The Blockbuster Hackathon.

**Live demo:** https://reel-director-949736914984.us-central1.run.app

## What it produces

- **Campaign Pack:** Hybrid Reel, Static Post, five-card Carousel Post, Slideshow Reel, and Reel cover from one approved direction.
- **Hybrid Reel:** one selected Veo 3.1 Fast hero shot with native audio, followed by deterministic product-proof frames, motion copy, captions, logo, and CTA.
- **Static Post:** a generated visual base composed into a deterministic 1080×1350 brand layout.
- **Carousel Post:** five ordered 1080×1350 campaign cards.
- **Slideshow Reel:** animated campaign cards in a 1080×1920 MP4 without a Veo call.
- **Full Video Reel:** two or three Veo shots for the higher-cost cinematic path.

## Why it is agentic

Reel Director places bounded decisions before expensive generation:

1. Controlled intake asks at most one clarification and always offers Skip.
2. Parallel Search gathers current, directly relevant source evidence.
3. Gemini turns the brief and evidence into a research plan, synthesis, three creative directions, and a structured shot plan.
4. Director Studio shows three candidate shots before Veo is invoked.
5. The user chooses both the output economics and the shot to produce.
6. Veo and Gemini image generation create media; Pillow and FFmpeg enforce exact brand layout, caption safety, dimensions, and delivery.

The default Hybrid path generates one selected Veo shot instead of automatically paying for all three candidates.

## Runtime architecture

```text
React + Vite studio
        │
        ▼
FastAPI orchestration
  ├── controlled brief and file/URL context
  ├── Parallel Search API ─ live evidence
  ├── Gemini via google-genai ─ structured decisions
  ├── Veo 3.1 Fast ─ native-audio vertical footage
  ├── Gemini image generation ─ still-image base
  ├── Pillow + FFmpeg ─ deterministic finishing
  └── private Google Cloud Storage ─ media storage/delivery
```

The source imports and calls both the official `parallel-web` SDK and the Google `google-genai` SDK at runtime. Parallel integration is in `backend/app/services/parallel_service.py`; Gemini, image, and Veo calls are in `backend/app/services/gemini_service.py`, `image_service.py`, and `veo_service.py`.

## Product surfaces

- Workspace shell: New Campaign, Campaigns, Assets, Brand Kit, Settings
- Persistent Demo User campaign history
- Reusable asset and brand libraries
- URL, image, video, PDF, DOCX, TXT, and Markdown context intake
- Separate interface language and campaign/output language
- Three candidate previews with explicit output-cost choices
- Branded playback and separate downloads
- Local workspace-scoped media proxy with HTTP Range seeking
- Private GCS delivery without OAuth tokens in client URLs

## Local quick start

Prerequisites: Python 3.11+, Node.js 20+, npm, and FFmpeg.

```powershell
Copy-Item .env.example .env

cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The checked-in environment example uses deterministic demo mode and contains placeholders only.

For live providers, set server-side values for `PARALLEL_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GCS_BUCKET_NAME`, configure Google Application Default Credentials, and set `DEMO_MODE=false`. Credentials must never be placed in the frontend.

## Deterministic verification

Automated tests do not invoke paid provider calls.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm ci
npm run build
```

The suite covers controlled intake, workspace state, URL/file security boundaries, Parallel result curation, output-format economics, single-shot locking, Veo prompt contracts, branded dimensions, media access, and HTTP Range behavior.

## Container deployment

The multi-stage Docker image builds the React app, installs the Python runtime and FFmpeg, and serves both the SPA and API from one Cloud Run service.

```powershell
docker build --target runtime -t reel-director .
docker run --rm -p 8080:8080 --env-file .env reel-director
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for private GCS, Secret Manager, service-account, and Cloud Run instructions.

## Repository privacy

This public repository intentionally excludes environment files, credentials, campaign databases, uploaded assets, generated media, logs, local virtual environments, build output, and test recordings. `.env.example` contains placeholders only. Public demonstration material should use a fictional brand and original assets.

## Current limitations

The hackathon build stores campaign and library metadata in local JSON files. That is appropriate for a single-instance demonstration but is not durable across Cloud Run instance replacement. A general production release should move state to Firestore or Cloud SQL and add real authentication, quotas, billing controls, and background job infrastructure.

Released under the [MIT License](LICENSE).
