import os
import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routes.ingest import router as ingest_router
from routes.chat import router as chat_router
from middleware.service_auth import verify_service_auth  # Add this

app = FastAPI(
    title="Axiora-AI Enterprise Knowledge Base", 
    version="1.0",
    dependencies=[Depends(verify_service_auth)]  # Apply globally
)

# CORS - allow Node.js origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("NODEJS_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup static files and templates
if not os.path.exists("public"):
    os.makedirs("public")
app.mount("/static", StaticFiles(directory="public"), name="static")

if not os.path.exists("views"):
    os.makedirs("views")
templates = Jinja2Templates(directory="views")

# Register API routes
app.include_router(ingest_router, prefix="/api")
app.include_router(chat_router, prefix="/api")

@app.get("/")
def serve_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "axiora-python-engine"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)