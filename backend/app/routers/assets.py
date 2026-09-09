import io
import os
import zipfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
from PIL import Image, UnidentifiedImageError

from app.dependencies import get_workspace_id
from app.models.library import AssetRecord, AssetSummary
from app.services.context_service import context_service
from app.services.library_store import asset_store, workspace_storage_dir


router = APIRouter(prefix="/api/assets", tags=["assets"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 60_000_000
MAX_DOCX_ENTRIES = 2_048
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

TYPE_MAP = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".txt": ("text", "text/plain"),
    ".md": ("text", "text/markdown"),
}


def _validate_image_content(extension: str, content: bytes) -> None:
    expected_format = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
    }[extension]
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != expected_format:
                raise ValueError("Image contents do not match the filename")
            if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions are not supported")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("Image file is invalid or corrupted") from exc


def _validate_docx_content(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                raise ValueError("DOCX contains too many embedded files")
            names = {info.filename.replace("\\", "/") for info in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("File is not a valid DOCX document")
            total_size = 0
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                path = Path(normalized)
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted DOCX files are not supported")
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("DOCX contains an unsafe embedded path")
                total_size += info.file_size
                if total_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise ValueError("DOCX expands beyond the safe processing limit")
    except zipfile.BadZipFile as exc:
        raise ValueError("DOCX file is invalid or corrupted") from exc


def validate_asset_content(extension: str, content: bytes) -> None:
    """Reject extension spoofing and malformed files before persistence or analysis."""
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        _validate_image_content(extension, content)
        return
    if extension in {".mp4", ".mov"}:
        if len(content) < 12 or content[4:8] != b"ftyp":
            raise ValueError("Video contents do not match an MP4/MOV file")
        return
    if extension == ".pdf":
        if not content.lstrip().startswith(b"%PDF-"):
            raise ValueError("File contents do not match a PDF document")
        return
    if extension == ".docx":
        _validate_docx_content(content)
        return
    if extension in {".txt", ".md"}:
        if b"\x00" in content:
            raise ValueError("Text files cannot contain binary data")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must use UTF-8 encoding") from exc


def to_summary(asset: AssetRecord) -> AssetSummary:
    return AssetSummary(
        asset_id=asset.asset_id,
        name=asset.name,
        kind=asset.kind,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        source_url=asset.source_url,
        text_preview=asset.extracted_text[:240],
        created_at=asset.created_at,
    )


def get_owned_asset(asset_id: str, workspace_id: str) -> AssetRecord:
    asset = asset_store.get(asset_id)
    if not asset or asset.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("", response_model=List[AssetSummary])
def list_assets(workspace_id: str = Depends(get_workspace_id)):
    assets = [asset for asset in asset_store.data.values() if asset.workspace_id == workspace_id]
    assets.sort(key=lambda asset: asset.created_at, reverse=True)
    return [to_summary(asset) for asset in assets]


@router.post("", response_model=AssetSummary)
async def upload_asset(file: UploadFile = File(...), workspace_id: str = Depends(get_workspace_id)):
    safe_name = Path(file.filename or "asset").name
    extension = Path(safe_name).suffix.lower()
    if extension not in TYPE_MAP:
        raise HTTPException(status_code=415, detail="Unsupported asset type")
    kind, canonical_mime = TYPE_MAP[extension]
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Asset exceeds 25 MB limit")
    if not content:
        raise HTTPException(status_code=400, detail="Asset is empty")
    try:
        validate_asset_content(extension, content)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    record = AssetRecord(
        workspace_id=workspace_id,
        name=safe_name,
        kind=kind,
        mime_type=canonical_mime,
        size_bytes=len(content),
    )
    target_dir = workspace_storage_dir(workspace_id)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, f"{record.asset_id}{extension}")
    with open(target_path, "wb") as handle:
        handle.write(content)
    record.storage_key = target_path
    try:
        if kind in {"pdf", "docx", "text"}:
            record.extracted_text = context_service.extract_file_text(target_path, kind)
        asset_store.save(record.asset_id, record)
    except Exception:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise
    return to_summary(record)


class ImportUrlRequest(BaseModel):
    url: str
    name: str = "Website context"


@router.post("/url", response_model=AssetSummary)
async def import_url(req: ImportUrlRequest, workspace_id: str = Depends(get_workspace_id)):
    try:
        safe_url = context_service.validate_url_syntax(req.url)
        text = await context_service.fetch_url_text(safe_url)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = AssetRecord(
        workspace_id=workspace_id,
        name=req.name.strip() or "Website context",
        kind="url",
        mime_type="text/html",
        source_url=safe_url,
        size_bytes=len(text.encode("utf-8")),
        extracted_text=text,
    )
    asset_store.save(record.asset_id, record)
    return to_summary(record)


@router.get("/{asset_id}/content")
def asset_content(asset_id: str, workspace_id: str = Depends(get_workspace_id)):
    asset = get_owned_asset(asset_id, workspace_id)
    if not asset.storage_key or not os.path.isfile(asset.storage_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset content not found")
    return FileResponse(asset.storage_key, media_type=asset.mime_type, filename=asset.name)
