import os
import sys
import asyncio
import uvicorn

# CRITICAL: This must be the very first thing that happens
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routes.ingest import router as ingest_router
from routes.chat import router as chat_router

app = FastAPI(title="axiora-AI enterprise knowledge base", version="1.0")

if not os.path.exists("public"):
    os.makedirs("public")
app.mount("/static", StaticFiles(directory="public"), name="static")

if not os.path.exists("views"):
    os.makedirs("views")
templates = Jinja2Templates(directory="views")

app.include_router(ingest_router, prefix="/api")
app.include_router(chat_router, prefix="/api")

@app.get("/")
def serve_frontend(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    # Use the string 'main:app' to allow the reloader to work 
    # without breaking the proactor loop
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)