import logging
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from config import config
from core.database import ChatDatabase
from core.sessions import SessionManager
from core.llm import DeepSeekLLM
from core.summaries import SummaryService
from core.api import create_api_router

# ====================== LOGGING SETUP ======================
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log') if config.DEBUG else None
    ]
)
logger = logging.getLogger(__name__)

# ====================== LIFESPAN MANAGEMENT ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Enhanced lifespan manager with startup/shutdown logging."""
    try:
        logger.info("Starting application services...")
        
        # Initialize core services
        db = ChatDatabase(config.DATABASE_PATH)
        session_manager = SessionManager(
            session_dir=config.SESSION_DIR,
            ttl_days=config.SESSION_TTL_DAYS
        )
        llm = DeepSeekLLM()
        summary_service = SummaryService(db)
        
        # Verify services
        await llm.health_check()  # Pre-flight LLM check
        session_manager.cleanup_expired()  # Initial cleanup
        
        # Inject dependencies
        app.state.db = db
        app.state.session_manager = session_manager
        app.state.llm = llm
        app.state.summary_service = summary_service
        
        logger.info(f"Services initialized | Debug: {config.DEBUG} | Persistence Default: {config.PERSISTENT_SESSIONS_DEFAULT}")
        yield
        
    except Exception as e:
        logger.critical(f"Startup failed: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down services...")
        db.close_all()
        logger.info("Application shutdown complete")

# ====================== APPLICATION FACTORY ======================
def create_app() -> FastAPI:
    app = FastAPI(
        title="Chatbot API",
        lifespan=lifespan,
        debug=config.DEBUG,
        description=f"API for conversational AI | Default persistence: {config.PERSISTENT_SESSIONS_DEFAULT}",
        version="1.0.0"
    )

    # Include API routes
    app.include_router(create_api_router())
    
    @app.get("/")
    async def root():
        return {
            "status": "running",
            "persistence_default": config.PERSISTENT_SESSIONS_DEFAULT,
            "debug_mode": config.DEBUG
        }

    return app

# ====================== ENTRY POINT ======================
if __name__ == "__main__":
    uvicorn.run(
        "main:create_app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.DEBUG,
        factory=True,
        server_header=False,
        log_level="debug" if config.DEBUG else "info"
    )