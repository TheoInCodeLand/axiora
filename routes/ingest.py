# routes/ingest.py
import os
import uuid
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Set
from urllib.parse import urlparse
from functools import wraps

from fastapi import (
    APIRouter, 
    HTTPException, 
    Query, 
    BackgroundTasks, 
    Request,
    status,
    Header
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl, validator
import httpx

from services.scraper import crawl_and_scrape, deep_crawl_website
from services.vector_service import process_and_store
from database.vector_db import get_pinecone_index

router = APIRouter()

# ============================================================================
# CONFIGURATION & STATE MANAGEMENT
# ============================================================================

# In-memory job tracking (replace with Redis in production)
# Structure: {job_id: JobStatus}
job_store: Dict[str, dict] = {}

# Rate limiting storage (replace with Redis in production)
# Structure: {customer_id: [timestamp1, timestamp2, ...]}
rate_limit_store: Dict[str, list] = {}

# Configuration
MAX_PAGES_LIMIT = 5000
INGEST_RATE_LIMIT = 5  # per hour per customer
INGEST_RATE_WINDOW = 3600  # 1 hour in seconds
JOB_TIMEOUT_HOURS = 24

# Allowed domains whitelist (empty = allow all valid public domains)
ALLOWED_DOMAINS: Set[str] = set()
BLOCKED_DOMAINS: Set[str] = {
    'localhost', '127.0.0.1', '0.0.0.0', '::1',
    '169.254.169.254',  # AWS metadata
    'metadata.google.internal',  # GCP metadata
    '192.168.', '10.', '172.'  # Private IP ranges
}


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class IngestRequest(BaseModel):
    url: HttpUrl
    customer_id: str = "demo_user_01"
    max_pages: int = 500
    dynamic: bool = True
    wait_for_api: Optional[str] = None
    crawl_depth: int = 5
    enable_screenshots: bool = False
    
    @validator('max_pages')
    def validate_max_pages(cls, v):
        if v < 1:
            raise ValueError('max_pages must be at least 1')
        if v > MAX_PAGES_LIMIT:
            raise ValueError(f'max_pages cannot exceed {MAX_PAGES_LIMIT}')
        return v
    
    @validator('customer_id')
    def validate_customer_id(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError('customer_id must be at least 3 characters')
        # Prevent injection attacks
        if any(c in v for c in ['..', '/', '\\', '$', '{', '}', '<', '>']):
            raise ValueError('customer_id contains invalid characters')
        return v.strip()
    
    @validator('crawl_depth')
    def validate_depth(cls, v):
        if v < 0 or v > 10:
            raise ValueError('crawl_depth must be between 0 and 10')
        return v


class IngestResponse(BaseModel):
    status: str
    job_id: str
    message: str
    estimated_duration: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class DeleteRequest(BaseModel):
    url: HttpUrl
    customer_id: str


# ============================================================================
# SECURITY & VALIDATION
# ============================================================================

def is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to private/internal IP."""
    if not hostname:
        return True
    
    hostname_lower = hostname.lower()
    
    # Check blocked domains
    for blocked in BLOCKED_DOMAINS:
        if blocked in hostname_lower:
            return True
    
    # Check for IP patterns
    import re
    # AWS metadata
    if re.match(r'^169\.254\.', hostname):
        return True
    # Private ranges
    if re.match(r'^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)', hostname):
        return True
    
    return False


def validate_url_security(url: str) -> str:
    """
    Comprehensive URL security validation.
    Prevents SSRF, local file access, and internal network attacks.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL format"
        )
    
    # Scheme validation
    allowed_schemes = {'http', 'https'}
    if parsed.scheme not in allowed_schemes:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme must be http or https, got: {parsed.scheme}"
        )
    
    # Host validation
    if not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail="URL must have a valid hostname"
        )
    
    # Block private IPs and internal services
    if is_private_ip(parsed.hostname):
        raise HTTPException(
            status_code=403,
            detail="Access to internal addresses is not allowed"
        )
    
    # Port validation (block common internal ports)
    if parsed.port and parsed.port in [22, 23, 25, 3306, 5432, 6379, 9200, 27017]:
        raise HTTPException(
            status_code=403,
            detail="Access to restricted ports is not allowed"
        )
    
    # Whitelist check (if configured)
    if ALLOWED_DOMAINS and parsed.hostname not in ALLOWED_DOMAINS:
        raise HTTPException(
            status_code=403,
            detail="Domain not in allowed list"
        )
    
    return url


def check_rate_limit(customer_id: str) -> bool:
    """
    Check if customer has exceeded ingest rate limit.
    Returns True if allowed, False if rate limited.
    """
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=INGEST_RATE_WINDOW)
    
    # Get existing requests for this customer
    requests = rate_limit_store.get(customer_id, [])
    
    # Filter to recent requests only
    recent_requests = [
        req_time for req_time in requests 
        if req_time > window_start
    ]
    
    # Check limit
    if len(recent_requests) >= INGEST_RATE_LIMIT:
        return False
    
    # Update store
    recent_requests.append(now)
    rate_limit_store[customer_id] = recent_requests
    
    return True


def generate_job_id(customer_id: str, url: str) -> str:
    """Generate deterministic job ID for idempotency."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M")
    hash_input = f"{customer_id}:{url}:{timestamp}"
    hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
    return f"ingest_{customer_id}_{hash_suffix}"


# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

async def _process_ingestion_job(
    job_id: str,
    url: str,
    customer_id: str,
    max_pages: int,
    crawl_depth: int,
    enable_screenshots: bool,
    wait_for_api: Optional[str]
):
    """
    Background task for heavy ingestion processing.
    Updates job_store with progress and results.
    """
    start_time = datetime.utcnow()
    
    try:
        # Update status to processing
        job_store[job_id].update({
            "status": "processing",
            "updated_at": start_time.isoformat(),
            "progress": {
                "stage": "crawling",
                "pages_found": 0,
                "pages_processed": 0,
                "chunks_created": 0
            }
        })
        
        print(f"\n{'='*70}")
        print(f"🚀 BACKGROUND INGEST STARTED: {job_id}")
        print(f"   URL: {url}")
        print(f"   Customer: {customer_id}")
        print(f"   Max Pages: {max_pages}")
        print(f"{'='*70}")
        
        # Phase 1: Deep Crawl
        crawled_pages = await deep_crawl_website(
            url=url,
            max_pages=max_pages,
            # Additional parameters passed via kwargs if needed
        )
        
        if not crawled_pages:
            raise ValueError("No content extracted. Site may block scrapers or require authentication.")
        
        total_pages = len(crawled_pages)
        job_store[job_id]["progress"].update({
            "stage": "vectorizing",
            "pages_found": total_pages
        })
        
        print(f"\n📊 Processing {total_pages} pages to vectors...")
        
        # Phase 2: Vector Processing
        total_chunks = 0
        processed_pages = 0
        
        for page in crawled_pages:
            try:
                page_url = page["url"]
                page_content = page["content"]
                
                # Skip pages with insufficient content
                if len(page_content) < 100:
                    print(f"   ⚠️  Skipping {page_url}: insufficient content")
                    continue
                
                chunks = await process_and_store(customer_id, page_url, page_content)
                total_chunks += chunks
                processed_pages += 1
                
                # Update progress
                job_store[job_id]["progress"].update({
                    "pages_processed": processed_pages,
                    "chunks_created": total_chunks
                })
                
                print(f"   💾 {page_url}: {chunks} chunks")
                
                # Small delay to prevent overwhelming Pinecone
                await asyncio.sleep(0.1)
                
            except Exception as page_error:
                print(f"   ❌ Error processing page {page.get('url', 'unknown')}: {page_error}")
                continue
        
        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Update final status
        job_store[job_id].update({
            "status": "completed",
            "updated_at": datetime.utcnow().isoformat(),
            "result": {
                "pages_crawled": total_pages,
                "pages_processed": processed_pages,
                "chunks_saved": total_chunks,
                "duration_seconds": duration,
                "base_url": url
            }
        })
        
        print(f"\n✅ INGEST COMPLETE: {total_chunks} chunks in {duration:.1f}s")
        
        # Notify Node.js backend (webhook)
        await _notify_webhook(job_id, customer_id, "completed", job_store[job_id]["result"])
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ INGEST FAILED: {error_msg}")
        
        job_store[job_id].update({
            "status": "failed",
            "updated_at": datetime.utcnow().isoformat(),
            "error": error_msg
        })
        
        # Notify Node.js of failure
        await _notify_webhook(job_id, customer_id, "failed", {"error": error_msg})


async def _notify_webhook(
    job_id: str, 
    customer_id: str, 
    status: str, 
    data: dict
):
    """Notify Node.js backend of job completion."""
    webhook_url = os.getenv("NODE_WEBHOOK_URL")
    if not webhook_url:
        print("   ⚠️  NODE_WEBHOOK_URL not set in Python .env")
        return
    
    # Grab the shared secret from Python's environment
    service_secret = os.getenv("SERVICE_SECRET", "")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url, 
                json={
                    "job_id": job_id,
                    "customer_id": customer_id,
                    "status": status,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data
                },
                headers={"X-Service-Secret": service_secret} 
            )
            
            # THE FIX: Force Python to print Node.js's exact response!
            print(f"   📡 Webhook Sent! Node.js replied with status: {response.status_code}")
            if response.status_code != 200:
                print(f"   ⚠️ Webhook Error Response: {response.text}")
                
    except Exception as e:
        print(f"   ⚠️  Webhook network connection failed: {e}")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Ingestion job accepted and processing"},
        429: {"description": "Rate limit exceeded"},
        400: {"description": "Invalid request parameters"},
        403: {"description": "URL not allowed"}
    }
)
async def ingest_url(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: IngestRequest
):
    """
    Start an asynchronous ingestion job.
    
    Returns immediately with a job ID. Use /ingest/status/{job_id} to track progress.
    """
    # Convert HttpUrl to string
    url_str = str(payload.url)
    customer_id = payload.customer_id
    
    # Security validation
    validate_url_security(url_str)
    
    # Rate limiting
    if not check_rate_limit(customer_id):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {INGEST_RATE_LIMIT} ingestions per hour."
        )
    
    # Generate job ID (idempotent for duplicate detection)
    job_id = generate_job_id(customer_id, url_str)
    
    # Check for existing active job
    if job_id in job_store:
        existing = job_store[job_id]
        if existing["status"] in ["pending", "processing"]:
            return IngestResponse(
                status="already_running",
                job_id=job_id,
                message="An ingestion job for this URL is already in progress",
                estimated_duration="Check status endpoint for progress"
            )
    
    # Initialize job record
    job_store[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "customer_id": customer_id,
        "url": url_str,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "progress": None,
        "result": None,
        "error": None
    }
    
    # Start background processing
    background_tasks.add_task(
        _process_ingestion_job,
        job_id=job_id,
        url=url_str,
        customer_id=customer_id,
        max_pages=payload.max_pages,
        crawl_depth=payload.crawl_depth,
        enable_screenshots=payload.enable_screenshots,
        wait_for_api=payload.wait_for_api
    )
    
    # Estimate duration based on max_pages
    estimated_mins = max(1, payload.max_pages // 50)
    
    return IngestResponse(
        status="accepted",
        job_id=job_id,
        message=f"Ingestion job started for {url_str}",
        estimated_duration=f"~{estimated_mins}-{estimated_mins * 2} minutes"
    )


@router.get(
    "/ingest/status/{job_id}",
    response_model=JobStatusResponse,
    responses={
        404: {"description": "Job not found"}
    }
)
async def get_job_status(job_id: str):
    """
    Get the current status of an ingestion job.
    """
    if job_id not in job_store:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    job = job_store[job_id]
    
    # Clean up old completed jobs (optional housekeeping)
    created = datetime.fromisoformat(job["created_at"])
    if job["status"] in ["completed", "failed"]:
        age_hours = (datetime.utcnow() - created).total_seconds() / 3600
        if age_hours > JOB_TIMEOUT_HOURS:
            # Return status but mark for cleanup
            pass
    
    return JobStatusResponse(**job)


@router.get("/ingest/jobs/{customer_id}")
async def list_customer_jobs(customer_id: str, limit: int = Query(default=10, le=50)):
    """
    List recent ingestion jobs for a customer.
    """
    jobs = [
        job for job in job_store.values()
        if job["customer_id"] == customer_id
    ]
    jobs.sort(key=lambda x: x["created_at"], reverse=True)
    return {"jobs": jobs[:limit], "total": len(jobs)}


@router.delete("/delete")
async def delete_url_data(
    url: str = Query(..., description="URL to delete"),
    customer_id: str = Query(..., description="Customer ID"),
    x_service_secret: Optional[str] = Header(None, alias="X-Service-Secret")  
):
    """Delete all vector data for a specific URL and customer."""
    # Verify service auth if configured
    service_secret = os.getenv("SERVICE_SECRET")
    if service_secret and x_service_secret:
        import hmac
        if not hmac.compare_digest(x_service_secret, service_secret):
            raise HTTPException(status_code=403, detail="Invalid service authentication")
    
    print(f"\n🗑️  Delete request: {url} for {customer_id}")
    
    try:
        index = get_pinecone_index()
        
        # Validate inputs
        if not url or not customer_id:
            raise HTTPException(status_code=400, detail="url and customer_id required")
        
        # Delete by metadata filter
        delete_response = index.delete(
            namespace=customer_id,
            filter={"source_url": {"$eq": url}}
        )
        
        print(f"✅ Vectors deleted for {url} in namespace {customer_id}")
        return {
            "status": "success",
            "message": f"Knowledge base data deleted",
            "customer_id": customer_id,
            "url": url,
            "namespace": customer_id
        }
        
    except Exception as e:
        print(f"❌ Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Request cancellation of a running job.
    Note: Actual cancellation depends on implementation details.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    if job["status"] not in ["pending", "processing"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel job with status: {job['status']}"
        )
    
    # Mark for cancellation (actual implementation would need job control)
    job["status"] = "cancelling"
    job["updated_at"] = datetime.utcnow().isoformat()
    
    return {"status": "cancelling", "job_id": job_id}


# ============================================================================
# HEALTH & ADMIN
# ============================================================================

@router.get("/ingest/health")
async def ingest_health():
    """
    Health check for ingestion service.
    """
    # Check Pinecone connectivity
    try:
        index = get_pinecone_index()
        stats = index.describe_index_stats()
        pinecone_status = "healthy"
    except Exception as e:
        pinecone_status = f"unhealthy: {str(e)}"
    
    return {
        "service": "ingest",
        "status": "healthy" if pinecone_status == "healthy" else "degraded",
        "pinecone": pinecone_status,
        "active_jobs": len([j for j in job_store.values() if j["status"] in ["pending", "processing"]]),
        "total_jobs_tracked": len(job_store)
    }