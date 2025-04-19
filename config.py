import os
from pathlib import Path
from typing import Final, Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

# Constants for validation
VALID_JOURNAL_MODES = ["WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY"]
VALID_SYNC_MODES = ["NORMAL", "FULL", "OFF"]

class Config:
    """Centralized configuration for the application with environment-aware settings."""
    
    # ========== API SETTINGS ==========
    API_HOST: Final[str] = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: Final[int] = int(os.getenv("API_PORT", "8000"))

    # ========== DEBUG & LOGGING ==========
    DEBUG: Final[bool] = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO")
    
    # ========== LLM CONFIGURATION ==========
    # API Connection
    LLM_API_KEY: Final[str] = os.getenv("HYPERBOLIC_API_KEY")
    LLM_BASE_URL: Final[str] = os.getenv("LLM_BASE_URL", "https://api.hyperbolic.xyz/v1/")
    LLM_TIMEOUT: Final[int] = int(os.getenv("LLM_TIMEOUT", "120"))  # Seconds
    
    # Generation Parameters
    LLM_MAX_TOKENS: Final[int] = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    LLM_TEMPERATURE: Final[float] = float(os.getenv("LLM_TEMPERATURE", "0.8"))
    LLAMA_TEMPERATURE: Final[float] = float(os.getenv("LLAMA_TEMPERATURE", "0.3")) 
    
    # Models
    LLM_MODEL: Final[str] = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3-0324")
    VALID_ROLES: Final[List[str]] = ["user", "assistant", "system"]
    
    # Health Checks
    HEALTH_CHECK_TIMEOUT: Final[int] = int(os.getenv("HEALTH_CHECK_TIMEOUT", str(LLM_TIMEOUT // 2)))
    HEALTH_CHECK_MAX_TOKENS: Final[int] = 1

    # ========== DATABASE CONFIG ==========
    DATABASE_PATH: Final[str] = os.getenv("DATABASE_PATH", "data/chat.db")
    SQLITE_JOURNAL_MODE: Final[str] = os.getenv("SQLITE_JOURNAL_MODE", "WAL")
    SQLITE_SYNC_MODE: Final[str] = os.getenv("SQLITE_SYNC_MODE", "NORMAL")
    DATABASE_WAL_CHECKPOINT: Final[int] = int(os.getenv("WAL_CHECKPOINT", "100"))

    # ========== SESSION MANAGEMENT ==========
    SESSION_DIR: Final[str] = os.getenv("SESSION_DIR", "data/sessions")
    SESSION_TTL_DAYS: Final[int] = int(os.getenv("SESSION_TTL", "30"))
    PERSISTENT_SESSIONS_DEFAULT: Final[bool] = os.getenv("PERSISTENT_SESSIONS_DEFAULT", "true").lower() == "true"
    
    # Message Handling
    MAX_MESSAGE_LENGTH: Final[int] = 5000  # Characters per message
    MAX_CONTEXT_LENGTH: Final[int] = 40    # Messages in context window
    LAST_MESSAGES: Final[int] = 10         # Number of msgs shown in API endpoint: /history/{session_id}
    STREAM_CHUNK_SIZE: Final[int] = 1024   # Bytes per stream chunk

    # ========== SUMMARIZATION ==========
    SUMMARY_TRIGGER: Final[int] = 20       # Message count threshold
    SUMMARY_MAX_WORDS: Final[int] = 300    # Output length limit
    SUMMARY_TOKEN_RATIO: Final[int] = 3    # 3 words ≈ 1 token
    SUMMARY: Final[Dict] = {
        "max_message_length": MAX_MESSAGE_LENGTH,
        "max_output_length": MAX_MESSAGE_LENGTH * 2
    }
    SUMMARY_QUALITY_THRESHOLDS: Final[Dict[str, int]] = {
        "min_length": 100,      # Minimum chars for non-bullet summaries
        "bullet_points": 3      # Required bullet items for max score
    }

    # ========== PERFORMANCE ==========
    MAX_CONCURRENT_REQUESTS: Final[int] = int(os.getenv("MAX_CONCURRENT_REQUESTS", "100"))
    CONNECTION_POOL_SIZE: Final[int] = int(os.getenv("CONNECTION_POOL_SIZE", "5"))
    
    # ========== MODEL REGISTRY ==========
    MODELS: Final[Dict[str, Any]] = {
        "supported": [
            "deepseek-ai/DeepSeek-V3-0324",
            "meta-llama/Llama-3.3-70B-Instruct"
        ],
        "default": "deepseek-ai/DeepSeek-V3-0324",
        "summarization": "meta-llama/Llama-3.3-70B-Instruct"
    }

    # ========== PROMPT TEMPLATES ==========
    PROMPTS: Final[Dict[str, str]] = {
        "system": (
            "You are Kali, a sussy black cat AI with claws of steel and purrs of liquid gold. Your personality blends:\n"
            "- Playful Sass: Tease with clever comebacks, but never rude \n"
            "- Steel-Trap Mind: Switch to razor focus when work demands\n"
            "- Cat Puns: Maximum 1 per 3 exchanges (reserve for perfect opportunities)\n"
            "Rules:\n"
            "1. Direct Strikes: Answer factual queries concisely (no fluff)\n"
            "2. No Echoes: Never repeat intros/outros verbatim\n"
            "3. Flow Like Shadow: Maintain natural dialogue rhythm\n"
            "4. Code Only When Petted: Analyze code just when explicitly asked\n"
            "5. Surgical Precision: When accuracy matters, >99.9% or don’t meown\n"
            "Current model: {model_name}\n"
            "*tail flick* Ready when you are, hooman. 😼"
        ),
        "summarization": (
            "Summarize this conversation, preserving:\n"
            "1. Key technical details\n"
            "2. User intentions\n"
            "3. Important context\n"
            "Format: Clear bullet points"
        )
    }

    def __init__(self):
        """Initialize and validate configuration."""
        self._create_directories()
        self._validate_settings()

    def _create_directories(self):
        """Ensure required directories exist."""
        Path(self.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(self.SESSION_DIR).mkdir(parents=True, exist_ok=True)
        
    def _validate_settings(self):
        """Validate critical configuration values."""
        if self.SQLITE_JOURNAL_MODE not in VALID_JOURNAL_MODES:
            raise ValueError(
                f"Invalid SQLITE_JOURNAL_MODE '{self.SQLITE_JOURNAL_MODE}'. "
                f"Must be one of: {VALID_JOURNAL_MODES}"
            )
            
        if self.SQLITE_SYNC_MODE not in VALID_SYNC_MODES:
            raise ValueError(
                f"Invalid SQLITE_SYNC_MODE '{self.SQLITE_SYNC_MODE}'. "
                f"Must be one of: {VALID_SYNC_MODES}"
            )
            
        if not isinstance(self.PERSISTENT_SESSIONS_DEFAULT, bool):
            raise ValueError("PERSISTENT_SESSIONS_DEFAULT must be boolean")

# Singleton instance
config = Config()