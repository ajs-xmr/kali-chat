import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import json
from datetime import datetime, timedelta

from config import config
from .database import ChatDatabase

class SessionManager:
    """Manages chat sessions with persistence control and debug logging."""

    def __init__(self, session_dir: str, ttl_days: int = config.SESSION_TTL_DAYS):
        self.session_dir = Path(session_dir)
        self.ttl = timedelta(days=ttl_days)
        self._init_session_storage()
        logging.debug(f"Session manager initialized | Directory: {self.session_dir} | TTL: {ttl_days} days")

    def _init_session_storage(self) -> None:
        """Ensure session directory exists with debug logging."""
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            logging.debug(f"Verified session directory at {self.session_dir}")
        except Exception as e:
            logging.error(f"Failed to initialize session storage: {str(e)}")
            raise

    def _save_to_disk(self, session_id: str, data: Dict[str, Any]) -> None:
        """Save session metadata to disk with error handling."""
        session_file = self.session_dir / f"{session_id}.json"
        try:
            with open(session_file, 'w') as f:
                json.dump(data, f)
            logging.debug(f"Saved session metadata to {session_file}")
        except (IOError, json.JSONEncodeError) as e:
            logging.error(f"Failed to save session {session_id}: {str(e)}")
            raise

    def _load_from_disk(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session metadata with validation."""
        session_file = self.session_dir / f"{session_id}.json"
        if not session_file.exists():
            return None

        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
            
            # Validate TTL
            last_active = datetime.fromisoformat(data['last_active'])
            if datetime.now() - last_active > self.ttl:
                logging.debug(f"Session {session_id} expired (last active: {last_active})")
                return None
                
            logging.debug(f"Loaded valid session {session_id}")
            return data
        except Exception as e:
            logging.warning(f"Corrupted session file {session_file}: {str(e)}")
            return None

    def create_session(self, persistent: Optional[bool] = None) -> str:
        """Create new session with explicit persistence control."""
        if persistent is None:
            persistent = config.PERSISTENT_SESSIONS_DEFAULT
        
        session_id = str(uuid.uuid4())
        metadata = {
            'id': session_id,
            'persistent': persistent,
            'created_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat()
        }

        if persistent:
            try:
                ChatDatabase(config.DATABASE_PATH).create_session(session_id, persistent)
                logging.info(f"Created persistent session {session_id}")
            except Exception as e:
                logging.error(f"Failed to create DB session: {str(e)}")
                raise
        else:
            self._save_to_disk(session_id, metadata)
            logging.info(f"Created ephemeral session {session_id}")

        return session_id

    def get_or_create(self, session_id: Optional[str], persistent: Optional[bool] = None) -> str:
        """Get existing session or create new with persistence control."""
        if not session_id:
            logging.debug("No session ID provided - creating new")
            return self.create_session(persistent)

        if self.validate_session(session_id):
            logging.debug(f"Using existing valid session {session_id}")
            return session_id

        logging.debug(f"Invalid session {session_id} - creating replacement")
        return self.create_session(persistent)

    def validate_session(self, session_id: str) -> bool:
        """Check session validity with detailed state logging."""
        # Check disk first (ephemeral sessions)
        disk_data = self._load_from_disk(session_id)
        if disk_data:
            logging.debug(f"Valid ephemeral session: {session_id}")
            return True

        # Check database (persistent sessions)
        try:
            db = ChatDatabase(config.DATABASE_PATH)
            if db.is_persistent(session_id):
                logging.debug(f"Valid persistent session: {session_id}")
                return True
        except Exception as e:
            logging.error(f"Session validation failed for {session_id}: {str(e)}")

        logging.debug(f"Invalid session: {session_id}")
        return False

    def cleanup_expired(self) -> int:
        """Remove expired sessions with logging."""
        count = 0
        for session_file in self.session_dir.glob("*.json"):
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                
                if datetime.now() - datetime.fromisoformat(data['last_active']) > self.ttl:
                    session_file.unlink()
                    count += 1
                    logging.debug(f"Cleaned up expired session: {session_file.stem}")
            except Exception as e:
                logging.warning(f"Failed to clean up {session_file}: {str(e)}")

        logging.info(f"Session cleanup completed | Removed {count} expired sessions")
        return count

    def is_persistent(self, session_id: str) -> bool:
        """Explicit persistence check with debug logging."""
        try:
            db = ChatDatabase(config.DATABASE_PATH)
            persistent = db.is_persistent(session_id)
            logging.debug(f"Persistence check for {session_id}: {persistent}")
            return persistent
        except Exception as e:
            logging.error(f"Persistence check failed for {session_id}: {str(e)}")
            return False