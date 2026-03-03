import asyncio
import sys
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

def _isolated_scrape_runner(url: str):
    """Runs the scraper in a completely fresh, isolated Windows event loop."""
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def _scrape():
        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)
            if result.success:
                # --- THE FINAL FIX ---
                # We use raw_markdown, which is guaranteed to contain the extracted text
                return result.markdown.raw_markdown
            else:
                return f"Error: {result.error_message}"
    
    try:
        return loop.run_until_complete(_scrape())
    finally:
        loop.close()

async def suck_website_data(url: str):
    """FastAPI calls this, which offloads the heavy browser work to a separate thread."""
    print("--> [DEBUG] Spawning isolated thread for headless browser...")
    return await asyncio.to_thread(_isolated_scrape_runner, url)