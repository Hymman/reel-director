# Validation Report — 9 September 2026

This repository is a sanitized submission package. The checked-in deterministic suite does not invoke paid Gemini, Parallel, Veo, image-generation, or GCS calls.

## Security boundaries

- Environment files, credentials, local campaign databases, uploaded assets, generated media, logs, build output, and virtual environments are excluded.
- `.env.example` contains placeholders only.
- Google Cloud project and bucket identifiers are supplied at deployment time.
- OAuth access tokens and workspace identifiers are not placed in media URLs.
- URL intake rejects unsafe targets and uploaded content is treated as untrusted reference material.

## Runtime integration evidence

- `parallel-web` is imported and `AsyncParallel.search` is called in the live research path.
- `google-genai` is imported and called for Gemini structured outputs, image generation, and Veo video generation.
- Veo requests use a vertical 9:16 contract and request native audio unless the user chooses silent output.
- Pillow and FFmpeg apply deterministic branded finishing and preserve audio.

## Reproduction

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm ci
npm run build
```

The final public repository commit and deployed URL should be recorded in the Devpost submission after these checks pass.

## Final submission checks

- Frontend clean install: `npm ci` completed with 0 vulnerabilities.
- Frontend production build: `npm run build` completed successfully (Vite 6.4.3, 1,595 modules transformed).
- Backend deterministic suite on Windows: passed with one intentional skip.
- Docker test target: **96 passed, 1 skipped** in 49.05 seconds.
- Production container smoke test: `/health`, `/`, and `/campaigns/new` returned HTTP 200.
- Production container response headers included Content-Security-Policy and Strict-Transport-Security.
- Public runtime image built successfully as a multi-stage container.
