from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import json

class ConversationPhase(Enum):
    GREETING = auto()           # First contact, building rapport
    DISCOVERY = auto()          # Understanding the real need
    CLARIFICATION = auto()      # Resolving ambiguity
    SOLUTION_PRESENTATION = auto()  # Providing answers
    VERIFICATION = auto()       # "Did this solve your problem?"
    OBJECTION_HANDLING = auto() # Addressing concerns
    CLOSING = auto()            # Wrapping up naturally
    ESCALATION = auto()         # Human handoff

@dataclass
class ConversationContext:
    phase: ConversationPhase = ConversationPhase.GREETING
    user_emotion: str = "neutral"
    urgency_level: int = 1  # 1-5
    topic_confidence: float = 0.0
    discovered_intent: Optional[str] = None
    pending_clarification: Optional[str] = None
    rapport_score: int = 0  # Build over time
    user_preferences: Dict = field(default_factory=dict)
    conversation_turns: int = 0
    last_topic: Optional[str] = None