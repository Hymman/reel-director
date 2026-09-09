from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from fastapi.responses import StreamingResponse
from app.services.ffmpeg_service import ffmpeg_service
from app.dependencies import get_workspace_id
from app.services.state_store import campaign_store
from app.services.demo_media import demo_media_service
from app.config import settings
import re

router = APIRouter(prefix="/api/media", tags=["Media"])

@router.get("/reels/{filename}")
def stream_reel(filename: str, request: Request, workspace_id: str = Depends(get_workspace_id)):
    """
    Safely streams or downloads rendered final reel video from GCS with HTTP Range support.
    Zero tokens, credentials or secrets are exposed to the client or browser.
    """
    if not re.match(r"^[a-zA-Z0-9_\-]+\.mp4$", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename format")

    # Verify workspace ownership
    uuid_match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", filename)
    if not uuid_match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename missing campaign ID")
        
    campaign_id = uuid_match.group(1)
    campaign = campaign_store.get(campaign_id)
    if not campaign or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    allowed_video_urls = [url for url in [campaign.final_video_url, campaign.final_slideshow_url] if url]
    if not allowed_video_urls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    from urllib.parse import urlparse
    expected_filenames = {urlparse(url).path.split("/")[-1] for url in allowed_video_urls}
    if not filename or filename not in expected_filenames:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    if settings.demo_mode:
        from fastapi.responses import FileResponse
        try:
            return FileResponse(
                demo_media_service.ensure_video(campaign, filename),
                media_type="video/mp4",
                filename=filename,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Demo media rendering failed") from exc

    blob_name = f"final_reels/{filename}"
    blob = ffmpeg_service.bucket.blob(blob_name)
    if not blob.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")

    blob.reload()
    file_size = blob.size

    range_header = request.headers.get("range")
    if range_header:
        range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start >= file_size or end >= file_size or start > end:
                headers = {"Content-Range": f"bytes */{file_size}"}
                return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, headers=headers)

            content_length = end - start + 1
            data = blob.download_as_bytes(start=start, end=end)

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
            }
            return Response(content=data, status_code=status.HTTP_206_PARTIAL_CONTENT, headers=headers)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
        "Content-Disposition": f'inline; filename="{filename}"'
    }

    def iter_file():
        chunk_size = 1024 * 1024
        for start_byte in range(0, file_size, chunk_size):
            end_byte = min(start_byte + chunk_size - 1, file_size - 1)
            yield blob.download_as_bytes(start=start_byte, end=end_byte)

    return StreamingResponse(iter_file(), status_code=status.HTTP_200_OK, headers=headers)


@router.get("/posts/{filename}")
def stream_post(filename: str, workspace_id: str = Depends(get_workspace_id)):
    if not re.match(r"^[a-zA-Z0-9_\-]+\.png$", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename format")
    uuid_match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", filename)
    if not uuid_match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename missing campaign ID")
    campaign = campaign_store.get(uuid_match.group(1))
    if not campaign or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    from urllib.parse import urlparse
    allowed_image_urls = [url for url in [campaign.final_image_url, *campaign.final_carousel_urls] if url]
    expected_filenames = {urlparse(url).path.split("/")[-1] for url in allowed_image_urls}
    if filename not in expected_filenames:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    if settings.demo_mode:
        return Response(
            content=demo_media_service.image_bytes(campaign, filename, (1080, 1350)),
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300"},
        )
    blob = ffmpeg_service.bucket.blob(f"final_posts/{filename}")
    if not blob.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    data = blob.download_as_bytes()
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})

@router.get("/previews/{workspace_id_path}/{campaign_id}/{shot_id}.png")
def stream_preview(workspace_id_path: str, campaign_id: str, shot_id: str, request: Request, workspace_id: str = Depends(get_workspace_id)):
    """Stream workspace-isolated candidate shot preview still. No tokens in response."""
    if workspace_id_path != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace mismatch")
    campaign = campaign_store.get(campaign_id)
    if not campaign or campaign.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")
    # Verify shot exists in this campaign
    shot = None
    if campaign.shot_plan:
        for s in [*campaign.shot_plan.shots, *campaign.shot_plan.full_reel_shots]:
            if s.shot_id == shot_id:
                shot = s
                break
    if not shot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shot not found")

    blob_name = f"preview_stills/{workspace_id}/{campaign_id}/{shot_id}.png"
    try:
        blob = ffmpeg_service.bucket.blob(blob_name)
        if blob.exists():
            data = blob.download_as_bytes()
            return Response(content=data, media_type="image/png",
                          headers={"Cache-Control": "private, max-age=300"})
    except Exception:
        pass

    # Fallback: generate deterministic storyboard inline without GCS
    from app.services.preview_service import preview_service
    from app.services.library_store import brand_kit_store
    kit = brand_kit_store.get(workspace_id)
    from app.models.library import BrandKit
    if not kit:
        kit = BrandKit(workspace_id=workspace_id)
    image_bytes = preview_service.render_storyboard_for_shot(shot, kit)
    return Response(content=image_bytes, media_type="image/png",
                  headers={"Cache-Control": "private, max-age=60"})


@router.get("/covers/{filename}")
def stream_cover(filename: str, workspace_id: str = Depends(get_workspace_id)):
    """Stream workspace-isolated reel cover image. No tokens in response."""
    if not re.match(r"^[a-zA-Z0-9_\-]+\.png$", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename format")
    uuid_match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", filename)
    if not uuid_match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename missing campaign ID")
    campaign = campaign_store.get(uuid_match.group(1))
    if not campaign or campaign.workspace_id != workspace_id or not campaign.final_thumbnail_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
    from urllib.parse import urlparse
    expected_filename = urlparse(campaign.final_thumbnail_url).path.split("/")[-1]
    if filename != expected_filename:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
    if settings.demo_mode:
        return Response(
            content=demo_media_service.image_bytes(campaign, filename, (1080, 1920)),
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300"},
        )
    blob = ffmpeg_service.bucket.blob(f"final_covers/{filename}")
    if not blob.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not found")
    data = blob.download_as_bytes()
    return Response(content=data, media_type="image/png",
                  headers={"Cache-Control": "private, max-age=300"})
