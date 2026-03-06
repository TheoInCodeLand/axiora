# middleware/service_auth.py
import os
from fastapi import HTTPException, Header, Request
from typing import Optional

SERVICE_SECRET = os.getenv("SERVICE_SECRET")

async def verify_service_auth(request: Request, x_service_secret: Optional[str] = Header(None)):
    """
    Verify that the request comes from the Node.js backend.
    Skip auth for health checks and widget endpoints.
    """
    # Skip auth for certain paths
    public_paths = ["/health", "/docs", "/openapi.json"]
    if any(request.url.path.endswith(path) for path in public_paths):
        return True
    
    if not SERVICE_SECRET:
        # If no secret configured, allow (development mode)
        return True
    
    if not x_service_secret:
        raise HTTPException(status_code=403, detail="Invalid service authentication: missing header")
    
    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(x_service_secret, SERVICE_SECRET):
        raise HTTPException(status_code=403, detail="Invalid service authentication: wrong secret")
    
    return True