from fastapi import APIRouter, HTTPException
from services.scraper import suck_website_data
from services.vector_service import process_and_store

router = APIRouter()

@router.post("/ingest")
async def ingest_url(url: str, customer_id: str = "demo_user_01"):
    print("\n==================================================")
    print(f"🚀 NEW INGEST REQUEST: {url}")
    print("==================================================")
    
    try:
        print("--> [STEP 1] Starting Scraper Engine...")
        markdown_content = await suck_website_data(url)
        
        if not markdown_content or str(markdown_content).strip() == "":
            print("--> [STEP 1 FAILED] Scraper returned empty content.")
            raise HTTPException(status_code=500, detail="Scraper returned no text.")
            
        # --- THE FIX ---
        # We only check if the string STARTS with our custom error prefix
        if str(markdown_content).startswith("Error:"):
             print(f"--> [STEP 1 FAILED] Scraper Error: {markdown_content[:200]}")
             raise HTTPException(status_code=500, detail=markdown_content[:200])

        print(f"--> [STEP 1 SUCCESS] Scraped {len(markdown_content)} characters.")

        print("--> [STEP 2] Sending text to Vector Service...")
        chunks_saved = await process_and_store(customer_id, url, markdown_content)

        print(f"--> [STEP 3] Finished! {chunks_saved} chunks saved to DB.")
        print("==================================================\n")

        return {
            "status": "Success",
            "url": url,
            "customer_id": customer_id,
            "chunks_saved_to_db": chunks_saved
        }
    except Exception as e:
        print(f"--> [FATAL ERROR] Pipeline crashed: {e}")
        raise HTTPException(status_code=500, detail=str(e))