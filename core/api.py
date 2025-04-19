from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging
from typing import AsyncGenerator, Optional
from datetime import datetime
from pydantic import ValidationError

from config import config
from .models import ChatRequest, ChatResponse, MessageHistory, ErrorResponse
from .service import ChatService
from .database import ChatDatabase
from .sessions import SessionManager
from .llm import DeepSeekLLM
from .summaries import SummaryService

router = APIRouter()

# Serve static files for frontend
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    router.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    logging.debug(f"Serving static files from {frontend_dir}")

def create_api_router() -> APIRouter:
    """Initialize API endpoints with enhanced logging and persistence control."""
    try:
        # Initialize services with debug logging
        db = ChatDatabase(config.DATABASE_PATH)
        session_manager = SessionManager(config.SESSION_DIR)
        llm = DeepSeekLLM()
        summary_service = SummaryService(db)
        service = ChatService(db, session_manager, llm, summary_service)
        logging.info("API services initialized successfully")
    except Exception as e:
        logging.critical(f"Failed to initialize services: {str(e)}", exc_info=True)
        raise

    # ====================== FRONTEND ENDPOINTS ======================
    @router.get("/", response_class=HTMLResponse)
    async def serve_frontend():
        """Serve frontend with cache control."""
        try:
            index_html = frontend_dir / "index.html"
            if not index_html.exists():
                logging.warning("Frontend not found - missing index.html")
                raise HTTPException(status_code=404, detail="Frontend not built")
            
            logging.debug("Serving frontend index.html")
            return HTMLResponse(
                content=index_html.read_text(),
                headers={"Cache-Control": "no-cache"}
            )
        except Exception as e:
            logging.error(f"Frontend serving failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Frontend unavailable")

    # ====================== API ENDPOINTS ======================
    @router.post("/chat", response_model=ChatResponse)
    async def handle_chat(
        request: ChatRequest,
        persistent: Optional[bool] = Query(
            None,
            description="Override default session persistence (config.PERSISTENT_SESSIONS_DEFAULT)"
        )
    ):
        """
        Process chat message with:
        - Session persistence control
        - Detailed error logging
        - Input validation
        """
        try:
            logging.debug(
                f"New chat request | Session: {request.session_id or 'new'} | "
                f"Persistent: {persistent if persistent is not None else 'config-default'}"
            )
            return await service.process_message(request)
            
        except ValidationError as e:
            logging.warning(
                f"Validation error for session {request.session_id or 'new'}: {str(e)}",
                exc_info=config.DEBUG
            )
            raise HTTPException(
                status_code=422,
                detail=ErrorResponse(
                    error="Validation Error",
                    details=str(e),
                    code=422,
                    allowed_values={
                        "max_message_length": config.MAX_MESSAGE_LENGTH,
                        "valid_roles": config.VALID_ROLES
                    }
                ).dict()
            )
            
        except Exception as e:
            logging.error(
                f"Chat processing failed for session {request.session_id or 'new'}: {str(e)}",
                exc_info=config.DEBUG
            )
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error="Internal Server Error",
                    details=str(e),
                    code=500
                ).dict()
            )

    @router.get("/chat/stream")
    async def stream_chat(
        message: str,
        session_id: Optional[str] = None,
        persistent: Optional[bool] = Query(None)
    ):
        """Streaming endpoint with session persistence support."""
        try:
            logging.debug(
                f"Starting stream | Session: {session_id or 'new'} | "
                f"Persistent: {persistent if persistent is not None else 'config-default'}"
            )
            
            async def generate_chunks() -> AsyncGenerator[str, None]:
                try:
                    async for chunk in service.stream_response(
                        ChatRequest(message=message, session_id=session_id)
                    ):
                        yield f"data: {chunk}\n\n"
                    yield "event: end\ndata: [DONE]\n\n"
                    logging.debug("Stream completed successfully")
                except Exception as e:
                    logging.error(f"Stream error: {str(e)}")
                    yield f"data: ⚠️ {str(e)}\n\n"
                    yield "event: error\ndata: [ERROR]\n\n"

            return StreamingResponse(
                generate_chunks(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Session-ID": session_id or "new"
                }
            )
            
        except Exception as e:
            logging.error(f"Stream setup failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Stream initialization failed")

    @router.get("/history/{session_id}", response_model=MessageHistory)
    async def get_history(session_id: str):
        """Retrieve chat history with persistence validation."""
        try:
            if not service.sessions.validate_session(session_id):
                logging.warning(f"Invalid history request for session {session_id}")
                raise HTTPException(
                    status_code=400,
                    detail=ErrorResponse(
                        error="Invalid Session",
                        details="Session expired or doesn't exist",
                        code=400
                    ).dict()
                )
            
            messages = service.db.get_messages(session_id, config.LAST_MESSAGES)
            summary = service.db.get_summary(session_id)
            logging.debug(f"Retrieved history for {session_id} ({len(messages)} messages)")
            
            return MessageHistory(
                messages=messages,
                summary=summary
            )
            
        except Exception as e:
            logging.error(f"History retrieval failed: {str(e)}")
            raise HTTPException(status_code=500, detail="History unavailable")

    # ====================== SYSTEM ENDPOINTS ======================
    @router.get("/health")
    async def health_check(request: Request):
        """Comprehensive health check with service verification."""
        try:
            llm_ok = await service.llm.health_check()
            frontend_ok = (frontend_dir / "index.html").exists()
            
            status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "services": {
                    "database": "ok",
                    "sessions": "ok",
                    "llm": "ok" if llm_ok else "unavailable",
                    "frontend": "ok" if frontend_ok else "not_detected"
                },
                "config": {
                    "persistent_sessions_default": config.PERSISTENT_SESSIONS_DEFAULT,
                    "summary_trigger": config.SUMMARY_TRIGGER
                }
            }
            logging.debug(f"Health check: {status}")
            return status
            
        except Exception as e:
            logging.critical(f"Health check failed: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail=ErrorResponse(
                    error="Service Unavailable",
                    details=str(e),
                    code=503
                ).dict()
            )

    return router