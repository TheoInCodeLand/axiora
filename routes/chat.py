# routes/chat.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
from services.chat_service import generate_answer

router = APIRouter()

class ChatPayload(BaseModel):
    question: str
    customer_id: str
    history: List[Dict] = []

class ChatResponse(BaseModel):
    answer: str
    phase: str
    sources_used: int
    confidence: float
    emotion_detected: str
    rapport_score: int

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatPayload):
    print(f"\n{'='*50}")
    print(f"🗣️  Customer: {payload.customer_id}")
    print(f"💬 Message: {payload.question[:50]}...")
    print(f"{'='*50}")
    
    try:
        result = await generate_answer(
            payload.customer_id,
            payload.question,
            payload.history
        )
        
        print(f"--------x Response generated | Phase: {result['phase']} | "
              f"Emotion: {result['emotion_detected']}")
        
        return ChatResponse(**result)
        
    except Exception as e:
        print(f"-------> Error: {e}")
        # Graceful degradation
        return ChatResponse(
            answer="I apologize, I'm having trouble processing that. "
                   "Could you rephrase, or would you prefer to speak with a human?",
            phase="ESCALATION",
            sources_used=0,
            confidence=0.0,
            emotion_detected="unknown",
            rapport_score=0
        )