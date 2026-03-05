import os
import sys
import asyncio

# --- THE WINDOWS ASYNCIO PATCH ---
# CRITICAL: This must happen before FastAPI or Uvicorn import their own event loops
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from routes.ingest import router as ingest_router
from routes.chat import router as chat_router

app = FastAPI(title="Axiora-AI Enterprise Knowledge Base", version="1.0")

# Setup static files and templates following the preferred folder structure
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

if __name__ == "__main__":
    # If the NotImplementedError ever returns, change reload=True to reload=False. 
    # Sometimes Uvicorn's hot-reloader tries to aggressively hijack the Windows event loop.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)