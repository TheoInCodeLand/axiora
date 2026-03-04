import asyncio
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import httpx

# (Keep the existing suck_website_data function here)

async def crawl_and_scrape(base_url: str, max_pages: int = 15):
    visited_urls = set()
    urls_to_visit = [base_url]
    scraped_data = []

    # Identify the root domain so the spider doesn't crawl away to external sites like Twitter
    base_domain = urlparse(base_url).netloc

    # Using httpx for highly efficient async HTTP requests
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        while urls_to_visit and len(visited_urls) < max_pages:
            current_url = urls_to_visit.pop(0)

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            print(f"--> [CRAWLER] Mapping & Scraping: {current_url}")

            try:
                response = await client.get(current_url)
                if response.status_code != 200:
                    continue

                # Extract all links on the current page to feed the spider
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    link_domain = urlparse(full_url).netloc

                    # Rule: Must be the same domain, must not be visited, and must not be a static file
                    if (link_domain == base_domain and 
                        full_url not in visited_urls and 
                        full_url not in urls_to_visit):
                        
                        if not any(full_url.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip', '.mp4', '.css', '.js']):
                            urls_to_visit.append(full_url)

                # Execute the original scraping logic for this specific page
                markdown_content = await suck_website_data(current_url)
                
                if markdown_content and not str(markdown_content).startswith("Error:"):
                    scraped_data.append({
                        "url": current_url,
                        "content": markdown_content
                    })

            except Exception as e:
                print(f"--> [CRAWLER] Failed to process {current_url}: {e}")

    return scraped_data