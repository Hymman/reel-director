from fastapi import APIRouter, HTTPException, Depends
from app.models.job import Job
from app.services.state_store import job_store
from app.dependencies import get_workspace_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, workspace_id: str = Depends(get_workspace_id)):
    job = job_store.get(job_id)
    if not job or job.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
