import hashlib
import os

from app.models.library import AssetRecord, BrandKit
from app.services.state_store import JsonFileStore


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
PRIVATE_ASSET_DIR = os.path.join(DATA_DIR, "private_assets")

asset_store = JsonFileStore(os.path.join(DATA_DIR, "assets.json"), AssetRecord)
brand_kit_store = JsonFileStore(os.path.join(DATA_DIR, "brand_kits.json"), BrandKit)


def workspace_storage_dir(workspace_id: str) -> str:
    workspace_hash = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:24]
    return os.path.join(PRIVATE_ASSET_DIR, workspace_hash)

