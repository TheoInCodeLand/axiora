import httpx
import asyncio
from datetime import datetime

async def test_webhook():
    # Test the diagnostic endpoint first
    try:
        response = await httpx.AsyncClient().post(
            "http://localhost:5000/engine/webhook/test",
            json={"job_id": "test_123", "status": "completed"},
            timeout=10.0
        )
        print(f"Test endpoint: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Test endpoint failed: {e}")

    # Test the actual webhook endpoint
    try:
        response = await httpx.AsyncClient().post(
            "http://localhost:5000/engine/webhook/ingest",
            headers={"X-Service-Secret": "your_engine_secret_here"},  # Match ENGINE_SECRET
            json={
                "job_id": "ingest_user_1_abc123",
                "customer_id": "user_1",
                "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "pages_crawled": 10,
                    "pages_processed": 10,
                    "chunks_saved": 25,
                    "duration_seconds": 45.2,
                    "base_url": "https://example.com"
                }
            },
            timeout=10.0
        )
        print(f"\nWebhook endpoint: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook delivered successfully!")
        elif response.status_code == 403:
            print("❌ Authentication failed - check X-Service-Secret header")
        elif response.status_code == 404:
            print("❌ Endpoint not found - check URL path")
            
    except Exception as e:
        print(f"\nWebhook endpoint failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_webhook())