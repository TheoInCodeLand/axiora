from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.chat_service import generate_answer

router = APIRouter()

# Define the expected JSON body
class ChatPayload(BaseModel):
    question: str
    customer_id: str = "demo_user_01" #change this to dynamic customer IDs in production

@router.post("/chat")
async def chat_endpoint(payload: ChatPayload):
    print("\n==================================================")
    print(f"🗣️ NEW CHAT REQUEST: {payload.question}")
    print("==================================================")
    
    try:
        response = await generate_answer(payload.customer_id, payload.question)
        print("==================================================\n")
        return response
    except Exception as e:
        print(f"--> [FATAL ERROR] Chat pipeline crashed: {e}")
        raise HTTPException(status_code=500, detail=str(e))