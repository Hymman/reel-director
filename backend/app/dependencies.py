from fastapi import Header, HTTPException, Request
from typing import Optional

WORKSPACE_COOKIE = "rd_workspace_id"


def get_workspace_id(request: Request, x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-ID")) -> str:
    """Resolve workspace scope from API header or the HttpOnly media-session cookie."""
    if x_workspace_id is not None:
        if not x_workspace_id.strip():
            raise HTTPException(status_code=400, detail="Missing X-Workspace-ID header")
        return x_workspace_id.strip()
    workspace_cookie = request.cookies.get(WORKSPACE_COOKIE, "").strip()
    if not workspace_cookie:
        raise HTTPException(status_code=400, detail="Missing X-Workspace-ID header or workspace session cookie")
    return workspace_cookie
