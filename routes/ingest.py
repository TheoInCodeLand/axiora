from fastapi import APIRouter, HTTPException
from services.scraper import crawl_and_scrape
from services.vector_service import process_and_store

router = APIRouter()

@router.post("/ingest")
async def ingest_url(url: str, customer_id: str = "demo_user_01", max_pages: int = 10):
    print("\n==================================================")
    print(f"🚀 NEW DOMAIN CRAWL REQUEST: {url}")
    print("==================================================")
    
    try:
        print(f"--> [STEP 1] Starting Autonomous Crawler (Max {max_pages} pages)...")
        # Trigger the spider instead of the single scraper
        crawled_pages = await crawl_and_scrape(url, max_pages)
        
        if not crawled_pages:
            print("--> [STEP 1 FAILED] Crawler returned no content.")
            raise HTTPException(status_code=500, detail="Crawler failed to extract any text.")

        print(f"--> [STEP 1 SUCCESS] Successfully mapped and scraped {len(crawled_pages)} pages.")

        print("--> [STEP 2] Sending all pages to Vector Service...")
        total_chunks_saved = 0

        # Loop through the list of dictionaries returned by the crawler
        for page in crawled_pages:
            # Send each page's specific URL and content to Pinecone
            chunks_saved = await process_and_store(customer_id, page["url"], page["content"])
            total_chunks_saved += chunks_saved

        print(f"--> [STEP 3] Finished! {total_chunks_saved} total chunks saved to DB across {len(crawled_pages)} pages.")
        print("==================================================\n")

        return {
            "status": "Success",
            "base_url": url,
            "pages_crawled": len(crawled_pages),
            "customer_id": customer_id,
            "chunks_saved_to_db": total_chunks_saved
        }
    except Exception as e:
        print(f"--> [FATAL ERROR] Pipeline crashed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/delete")
async def delete_url_data(url: str, customer_id: str):
    print(f"\n--> [SYSTEM] Request to delete vectors for: {url}")
    try:
        index = get_pinecone_index()
        
        # Pinecone allows us to delete vectors based on the metadata we injected earlier!
        index.delete(
            namespace=customer_id,
            filter={"source_url": {"$eq": url}}
        )
        
        print("--> [SUCCESS] Vectors purged from Pinecone.")
        return {"status": "Success", "message": "Knowledge base deleted."}
    except Exception as e:
        print(f"--> [FATAL ERROR] Failed to delete from Pinecone: {e}")
        raise HTTPException(status_code=500, detail=str(e))