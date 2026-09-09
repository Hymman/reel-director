from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    workspace_id: str = "legacy_workspace"
    stage: Literal["extracting", "planning", "research", "strategy", "direction", "generating", "assembling", "qa", "complete", "failed"]
    progress: int = 0
    message: str = "Starting job..."
    shot_status: Dict[str, Literal["queued", "generating", "ready", "failed"]] = Field(default_factory=dict)
    error_code: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
