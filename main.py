import sys
import asyncio

# CRITICAL: This must be the very first thing that happens
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from routes.ingest import router as ingest_router

app = FastAPI(title="Axiora-AI")
app.include_router(ingest_router, prefix="/api")

@app.get("/")
def home():
    return {"status": "Online"}

if __name__ == "__main__":
    import uvicorn
    # Use the string 'main:app' to allow the reloader to work 
    # without breaking the proactor loop
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)