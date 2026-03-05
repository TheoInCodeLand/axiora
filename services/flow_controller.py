from typing import Optional, Tuple
from .conversation_state import ConversationPhase, ConversationContext
from .emotional_intelligence import EmotionalIntelligence

class FlowController:
    """Manages conversation flow like a skilled consultant"""
    
    def __init__(self):
        self.phase_handlers = {
            ConversationPhase.GREETING: self._handle_greeting,
            ConversationPhase.DISCOVERY: self._handle_discovery,
            ConversationPhase.CLARIFICATION: self._handle_clarification,
            ConversationPhase.SOLUTION_PRESENTATION: self._handle_solution,
            ConversationPhase.VERIFICATION: self._handle_verification,
            ConversationPhase.OBJECTION_HANDLING: self._handle_objection,
            ConversationPhase.CLOSING: self._handle_closing,
        }
    
    async def determine_next_action(
        self, 
        user_message: str, 
        context: ConversationContext,
        retrieved_knowledge: list
    ) -> Tuple[ConversationPhase, Optional[str], dict]:
        """
        Returns: (next_phase, clarification_question_if_needed, metadata)
        """
        
        # Analyze current state
        emotion, urgency, confidence = EmotionalIntelligence.analyze(
            user_message, []
        )
        
        context.user_emotion = emotion
        context.urgency_level = urgency
        context.conversation_turns += 1
        
        # Check for topic shift
        if context.last_topic and EmotionalIntelligence.detect_conversation_shift(
            user_message, context.last_topic
        ):
            # User changed subjects - acknowledge and pivot
            return ConversationPhase.DISCOVERY, None, {
                "topic_shift": True,
                "previous_topic": context.last_topic
            }
        
        # Route to appropriate handler
        handler = self.phase_handlers.get(context.phase, self._handle_discovery)
        
        next_phase, clarification, meta = await handler(
            user_message, context, retrieved_knowledge
        )
        
        context.phase = next_phase
        context.last_topic = user_message
        
        return next_phase, clarification, meta
    
    async def _handle_greeting(self, message, context, knowledge):
        """First interaction - set tone and discover intent"""
        
        # If user jumps straight to question, skip to discovery
        if len(message) > 15 and any(word in message.lower() for word in ["how", "what", "why", "can", "issue", "problem"]):
            return ConversationPhase.DISCOVERY, None, {"skipped_greeting": True}
        
        # Build rapport, ask discovery question
        return ConversationPhase.DISCOVERY, None, {
            "rapport_building": True,
            "suggested_response": "greeting_with_discovery"
        }
    
    async def _handle_discovery(self, message, context, knowledge):
        """Understand the real underlying need"""
        
        # Check if we have enough context to answer
        if not knowledge and context.conversation_turns > 2:
            # No knowledge found after multiple turns - need clarification
            return ConversationPhase.CLARIFICATION, self._generate_clarification_question(message), {
                "knowledge_gap": True
            }
        
        if knowledge and len(knowledge) > 0:
            confidence = knowledge[0].get('score', 0)
            if confidence > 0.8:
                # High confidence - proceed to solution
                return ConversationPhase.SOLUTION_PRESENTATION, None, {
                    "confidence": confidence,
                    "source_count": len(knowledge)
                }
            else:
                # Medium confidence - present with caveat
                return ConversationPhase.SOLUTION_PRESENTATION, None, {
                    "confidence": confidence,
                    "needs_verification": True
                }
        
        # No knowledge - ask clarifying question
        return ConversationPhase.CLARIFICATION, self._generate_clarification_question(message), {
            "no_knowledge": True
        }
    
    async def _handle_clarification(self, message, context, knowledge):
        """Resolve ambiguity"""
        
        # Check if clarification was successful
        if context.pending_clarification:
            # We asked a question previously - did they answer it?
            if len(message) > 5:  # Simple heuristic
                context.pending_clarification = None
                return ConversationPhase.DISCOVERY, None, {"clarified": True}
        
        # Still need more info
        return ConversationPhase.CLARIFICATION, self._generate_clarification_question(message, context), {
            "still_unclear": True
        }
    
    async def _handle_solution(self, message, context, knowledge):
        """Present solution and check if it resolves the issue"""
        
        # After presenting solution, move to verification
        return ConversationPhase.VERIFICATION, None, {
            "solution_presented": True,
            "awaiting_feedback": True
        }
    
    async def _handle_verification(self, message, context, knowledge):
        """Check if solution worked"""
        
        # Analyze response for satisfaction signals
        emotion, _, _ = EmotionalIntelligence.analyze(message, [])
        
        if emotion == "satisfied":
            context.rapport_score += 1
            return ConversationPhase.CLOSING, None, {"solved": True}
        elif emotion == "frustrated" or "not working" in message.lower():
            return ConversationPhase.OBJECTION_HANDLING, None, {"solution_failed": True}
        else:
            # Unclear - ask directly
            return ConversationPhase.VERIFICATION, "Did that solve your issue, or would you like me to explore alternatives?", {
                "explicit_check": True
            }
    
    async def _handle_objection(self, message, context, knowledge):
        """Handle pushback or failed solutions"""
        
        context.rapport_score -= 1  # Friction in relationship
        
        if context.rapport_score < -2 or context.conversation_turns > 8:
            # Too much friction - escalate
            return ConversationPhase.ESCALATION, None, {"escalation_reason": "repeated_objections"}
        
        # Try alternative approach
        return ConversationPhase.DISCOVERY, None, {
            "alternative_approach": True,
            "acknowledge_frustration": True
        }
    
    async def _handle_closing(self, message, context, knowledge):
        """Natural conversation ending"""
        
        # Check if user has new question
        if any(word in message.lower() for word in ["also", "another", "additionally", "what about"]):
            return ConversationPhase.DISCOVERY, None, {"new_topic": True}
        
        # Proper close
        return ConversationPhase.CLOSING, None, {"end_conversation": True}
    
    def _generate_clarification_question(self, message, context=None):
        """Generate contextual clarification question"""
        
        # Extract potential topics from message
        words = message.lower().split()
        
        if any(word in words for word in ["it", "this", "that", "thing"]):
            return "Could you clarify what you're referring to? I want to make sure I give you the most accurate information."
        
        if "error" in words or "issue" in words:
            return "To help you best, could you tell me: 1) What you were trying to do, and 2) What happened instead?"
        
        if len(message) < 10:
            return "Could you provide a bit more detail about what you're looking for? I want to ensure I point you to exactly the right resource."
        
        return "I want to make sure I understand correctly. Are you asking about [paraphrase], or is there something more specific you need?"