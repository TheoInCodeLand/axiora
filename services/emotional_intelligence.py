import re
from typing import Tuple

class EmotionalIntelligence:
    """Detects emotional state and conversation dynamics"""
    
    FRUSTRATION_PATTERNS = [
        r"\b(stupid|useless|terrible|awful|hate|annoying)\b",
        r"\b(not working|doesn't work|broken|bug)\b",
        r"[!]{2,}",  # Multiple exclamation marks
        r"\b(again|still|yet|already)\b.*\b(not|never)\b",
        r"^[A-Z\s]{5,}$",  # ALL CAPS shouting
    ]
    
    URGENCY_PATTERNS = [
        r"\b(urgent|asap|immediately|emergency|critical)\b",
        r"\b(deadline|due|today|now|hurry)\b",
        r"\b(lost|down|broken|stopped)\b",
    ]
    
    CONFUSION_PATTERNS = [
        r"\b(confused|don't understand|unclear|what do you mean)\b",
        r"\b(how do I|where is|can't find)\b",
        r"\?",  # Multiple questions
    ]
    
    SATISFACTION_PATTERNS = [
        r"\b(thanks|thank you|great|awesome|perfect|helpful)\b",
        r"\b(worked|solved|fixed|figured out)\b",
    ]
    
    @classmethod
    def analyze(cls, message: str, history: list) -> Tuple[str, int, float]:
        """
        Returns: (emotion, urgency, confidence_in_assessment)
        """
        message_lower = message.lower()
        
        # Check frustration
        frustration_score = sum(
            1 for pattern in cls.FRUSTRATION_PATTERNS 
            if re.search(pattern, message_lower, re.IGNORECASE)
        )
        
        # Check urgency
        urgency_score = sum(
            1 for pattern in cls.URGENCY_PATTERNS 
            if re.search(pattern, message_lower, re.IGNORECASE)
        )
        
        # Check confusion
        confusion_score = sum(
            1 for pattern in cls.CONFUSION_PATTERNS 
            if re.search(pattern, message_lower, re.IGNORECASE)
        )
        
        # Check satisfaction
        satisfaction_score = sum(
            1 for pattern in cls.SATISFACTION_PATTERNS 
            if re.search(pattern, message_lower, re.IGNORECASE)
        )
        
        # Determine dominant emotion
        scores = {
            "frustrated": frustration_score,
            "urgent": urgency_score,
            "confused": confusion_score,
            "satisfied": satisfaction_score,
            "neutral": 0.5  # Baseline
        }
        
        emotion = max(scores, key=scores.get)
        
        # Calculate urgency level (1-5)
        urgency = min(5, 1 + urgency_score + (2 if emotion == "frustrated" else 0))
        
        # Confidence based on signal strength
        total_signals = sum(scores.values()) - 0.5  # Remove neutral baseline
        confidence = min(0.95, 0.3 + (total_signals * 0.15))
        
        return emotion, urgency, confidence
    
    @classmethod
    def detect_conversation_shift(cls, current_message: str, last_topic: str) -> bool:
        """Detect if user is changing subjects"""
        # Simple implementation - can be enhanced with embeddings
        current_keywords = set(current_message.lower().split())
        last_keywords = set(last_topic.lower().split()) if last_topic else set()
        
        overlap = len(current_keywords & last_keywords)
        total_unique = len(current_keywords | last_keywords)
        
        if total_unique == 0:
            return False
            
        similarity = overlap / total_unique
        return similarity < 0.3  # Less than 30% overlap = topic shift