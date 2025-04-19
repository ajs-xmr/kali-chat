import logging
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime

from .models import ChatRequest, ChatResponse
from .database import ChatDatabase
from .sessions import SessionManager
from .llm import DeepSeekLLM
from .summaries import SummaryService
from config import config

class ChatService:
    """Handles chat message processing with persistence awareness and detailed logging."""

    def __init__(
        self,
        db: ChatDatabase,
        session_manager: SessionManager,
        llm: DeepSeekLLM,
        summary_service: SummaryService
    ):
        """Initialize with dependency injection and debug logging."""
        self.db = db
        self.sessions = session_manager
        self.llm = llm
        self.summary_service = summary_service
        self.max_context_length = config.MAX_CONTEXT_LENGTH
        logging.info(
            f"ChatService initialized | Max context: {self.max_context_length} messages | "
            f"Summary trigger: every {config.SUMMARY_TRIGGER} messages"
        )

    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        Process a chat message with full persistence support.
        Returns validated response or error.
        """
        try:
            # Session handling
            session_id = self.sessions.get_or_create(
                request.session_id,
                persistent=getattr(request, 'persistent', None)
            )
            logging.debug(f"Processing message for session {session_id[:8]}...")

            # Save user message
            self._save_message(session_id, "user", request.message)
            logging.debug(f"Saved user message ({len(request.message)} chars)")

            # Generate response
            context = self._get_context(session_id)
            response = await self._generate_response(context)
            logging.debug(f"Generated LLM response ({len(response)} chars)")

            # Save AI response
            self._save_message(session_id, "assistant", response)
            
            # Conditional summarization
            await self._maybe_summarize(session_id)

            return ChatResponse(
                response=response,
                session_id=session_id,
                context_length=len(context)
            )

        except Exception as e:
            logging.error(
                f"Message processing failed for session {session_id[:8] if 'session_id' in locals() else 'N/A'}: {str(e)}",
                exc_info=config.DEBUG
            )
            raise

    async def stream_response(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        """Stream LLM response with session persistence support."""
        try:
            session_id = self.sessions.get_or_create(
                request.session_id,
                persistent=getattr(request, 'persistent', None)
            )
            logging.debug(f"Streaming response for session {session_id[:8]}")

            self._save_message(session_id, "user", request.message)
            
            full_response = ""
            async for chunk in self.llm.generate_response(
                self._get_context(session_id),
                stream=True
            ):
                full_response += chunk
                yield chunk

            self._save_message(session_id, "assistant", full_response)
            await self._maybe_summarize(session_id)
            logging.debug(f"Completed streaming ({len(full_response)} chars)")

        except Exception as e:
            logging.error(f"Stream failed for session {session_id[:8]}: {str(e)}")
            yield "⚠️ Error: Please try again"
            raise

    # ====================== PRIVATE METHODS ======================
    def _get_context(self, session_id: str) -> List[Dict[str, str]]:
        """
        Retrieve conversation context with:
        - System prompt injection (timestamp-free)
        - Message validation
        - Debug logging
        """
        try:
            # 1. Fetch messages from DB (preserves original functionality)
            db_messages = self.db.get_messages(session_id, self.max_context_length)
            
            # 2. Convert to dict format (exclude None timestamps)
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"timestamp": msg.timestamp.isoformat()} if msg.timestamp else {})
                }
                for msg in db_messages
            ]
            
            # 3. Inject system prompt if missing (timestamp not required)
            if not any(msg.get("role") == "system" for msg in messages):
                system_prompt = {
                    "role": "system",
                    "content": config.PROMPTS["system"].format(
                        model_name=config.MODELS["default"]
                    )
                    # Explicitly no timestamp
                }
                messages.insert(0, system_prompt)
                logging.debug(
                    f"Injected system prompt into {session_id[:8]} | "
                    f"Model: {config.MODELS['default']}"
                )
            
            # 4. Log context composition
            logging.debug(
                f"Context prepared for {session_id[:8]} | "
                f"Messages: {len(messages)}/{self.max_context_length} | "
                f"Roles: {set(m['role'] for m in messages)}"
            )
            
            return messages

        except Exception as e:
            logging.error(
                f"Context retrieval failed for {session_id[:8]} | "
                f"Error: {str(e)}",
                exc_info=config.DEBUG
            )
            raise

    async def _generate_response(self, context: List[Dict]) -> str:
        """Generate LLM response with error handling and timing."""
        try:
            start_time = datetime.now()
            async for response in self.llm.generate_response(context):
                elapsed = (datetime.now() - start_time).total_seconds()
                logging.debug(f"LLM response generated in {elapsed:.2f}s")
                return response
        except Exception as e:
            logging.error(f"LLM generation failed: {str(e)}")
            return "⚠️ I encountered an error processing your request."

    def _save_message(self, session_id: str, role: str, content: str):
        """Save message with validation and debug logging."""
        try:
            if not session_id:
                logging.warning("Attempted to save message without session_id")
                return

            self.db.add_message(session_id, role, content)
            logging.debug(f"Saved {role} message to {session_id[:8]} ({len(content)} chars)")
        except Exception as e:
            logging.error(f"Message save failed: {str(e)}")
            raise

    async def _maybe_summarize(self, session_id: str):
        """Conditionally trigger summarization with detailed logging."""
        try:
            if not self.sessions.is_persistent(session_id):
                logging.debug(f"Skipping summarization for ephemeral session {session_id[:8]}")
                return

            message_count = self.db.get_message_count(session_id)
            if message_count % config.SUMMARY_TRIGGER == 0:
                logging.info(
                    f"Triggering summarization for {session_id[:8]} "
                    f"(message count: {message_count})"
                )
                messages = self._get_context(session_id)
                summary = await self.summary_service.generate_summary(messages)
                
                if summary and not summary.startswith("⚠️"):
                    self.db.save_summary(session_id, summary)
                    logging.info(f"Saved summary for {session_id[:8]} ({len(summary)} chars)")
                else:
                    logging.warning(f"Summary generation failed for {session_id[:8]}")
        except Exception as e:
            logging.error(f"Summarization failed: {str(e)}", exc_info=config.DEBUG)
