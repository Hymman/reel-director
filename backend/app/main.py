from fastapi import FastAPI, Depends, Response, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.routers import assets, brand_kit, campaigns, jobs, media
from app.config import settings
from app.dependencies import get_workspace_id, WORKSPACE_COOKIE
from pathlib import Path

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

# In local development, React runs on 5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; img-src 'self' data: blob: https://storage.googleapis.com "
            "https://*.storage.googleapis.com; media-src 'self' blob: https://storage.googleapis.com "
            "https://*.storage.googleapis.com; connect-src 'self' http://localhost:5173 "
            "http://127.0.0.1:5173 ws://localhost:5173 ws://127.0.0.1:5173"
        )
    if settings.environment.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(campaigns.router)
app.include_router(jobs.router)
app.include_router(media.router)
app.include_router(assets.router)
app.include_router(brand_kit.router)


@app.post("/api/workspace/session")
def establish_workspace_session(response: Response, workspace_id: str = Depends(get_workspace_id)):
    """Enable native image/video requests without putting workspace identity in URLs."""
    response.set_cookie(
        key=WORKSPACE_COOKIE,
        value=workspace_id,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        path="/api/media",
    )
    return {"status": "ok"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "environment": settings.environment, "demo_mode": settings.demo_mode}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        requested = (frontend_dist / full_path).resolve()
        if requested.is_file() and frontend_dist.resolve() in requested.parents:
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
