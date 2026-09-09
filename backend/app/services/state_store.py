import json
import os
from typing import Dict, Optional, TypeVar, Generic, Type
from pydantic import BaseModel
from datetime import datetime, timezone
from app.models.campaign import Campaign
from app.models.job import Job

T = TypeVar("T", bound=BaseModel)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class JsonFileStore(Generic[T]):
    def __init__(self, file_path: str, model_cls: Type[T]):
        self.file_path = file_path
        self.model_cls = model_cls
        self.data: Dict[str, T] = {}
        self.raw_data: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.file_path):
            self.data = {}
            self.raw_data = {}
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                self.raw_data = json.load(f)
                self.data = {k: self.model_cls.model_validate(v) for k, v in self.raw_data.items()}
        except Exception:
            self.data = {}
            self.raw_data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.raw_data, f, indent=2)

    def get(self, id: str) -> Optional[T]:
        return self.data.get(id)

    def save(self, id: str, item: T):
        if hasattr(item, "updated_at"):
            item.updated_at = now_iso()
        self.data[id] = item
        self.raw_data[id] = item.model_dump(mode='json')
        self._save()

    def update(self, id: str, updates: dict) -> Optional[T]:
        if id in self.data:
            item = self.data[id]
            updated_data = item.model_dump(mode='json')
            updated_data.update(updates)
            if "updated_at" in self.model_cls.model_fields:
                updated_data["updated_at"] = now_iso()
            new_item = self.model_cls.model_validate(updated_data)
            self.data[id] = new_item
            self.raw_data[id] = new_item.model_dump(mode='json')
            self._save()
            return self.data[id]
        return None

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
campaign_store = JsonFileStore(os.path.join(DATA_DIR, "campaigns.json"), Campaign)
job_store = JsonFileStore(os.path.join(DATA_DIR, "jobs.json"), Job)
