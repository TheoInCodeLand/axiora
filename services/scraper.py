import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

def extract_clean_text(html):
    """Strips out headers, footers, and nav bars to keep only the core content."""
    soup = BeautifulSoup(html, "html.parser")

    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
        
    text = soup.get_text(separator="\n")
    return text

def get_internal_links(base_url, html):
    """Finds all valid internal links on a page."""
    soup = BeautifulSoup(html, "html.parser")
    internal_links = set()
    domain = urlparse(base_url).netloc

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href")
        if not href:
            continue
            
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        if parsed_url.netloc == domain:
            clean_url = full_url.split('#')[0]
            if not any(clean_url.lower().endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.jpeg', '.zip', '.mp4']) and not clean_url.startswith('mailto:'):
                internal_links.add(clean_url)
                
    return internal_links

async def suck_website_data(start_url: str, max_pages: int = 15):
    """
    Uses a headless browser to render JavaScript before crawling the domain.
    """
    visited = set()
    to_visit = [start_url]
    scraped_data = []

    print(f"\n--> [SYSTEM] Initiating Playwright Domain Crawl: {start_url} (Max {max_pages} pages)")
    
    # Launch the headless Chromium browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = await context.new_page()

        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            
            if current_url in visited:
                continue
                
            visited.add(current_url)
            print(f"--> [CRAWLER] Rendering page {len(visited)}/{max_pages}: {current_url}")
            
            try:
                # wait_until="networkidle" ensures dynamic React/Vue/Express data is fully loaded
                await page.goto(current_url, wait_until="networkidle", timeout=15000)
                html = await page.content()
            except Exception as e:
                print(f"--> [WARNING] Failed to render {current_url}: {e}")
                continue
                
            text_content = extract_clean_text(html)
            
            if text_content and len(text_content.strip()) > 50:
                scraped_data.append({
                    "url": current_url,
                    "content": text_content
                })
                
            new_links = get_internal_links(start_url, html)
            for link in new_links:
                if link not in visited and link not in to_visit:
                    to_visit.append(link)

        await browser.close()

    print(f"--> [SYSTEM] Crawl complete. Extracted {len(scraped_data)} fully-rendered pages.")
    return scraped_data