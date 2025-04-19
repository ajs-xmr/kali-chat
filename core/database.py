import sqlite3
import threading
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Iterator, Any
from datetime import datetime

from config import config
from .models import Message

class ChatDatabase:
    """SQLite database handler with timestamp fixes and enhanced validation."""

    def __init__(self, db_path: str = config.DATABASE_PATH) -> None:
        self.db_path = Path(db_path)
        self.connection_pool: List[sqlite3.Connection] = []
        self.pool_lock = threading.Lock()
        self._init_db()
        logging.debug(f"Database initialized at {self.db_path}")

    def _init_db(self) -> None:
        """Initialize database schema with strict typing and timestamp defaults."""
        with self._get_connection() as conn:
            try:
                # Performance settings
                conn.execute(f"PRAGMA journal_mode={config.SQLITE_JOURNAL_MODE}")
                conn.execute(f"PRAGMA synchronous={config.SQLITE_SYNC_MODE}")
                conn.execute("PRAGMA foreign_keys=ON")
                
                # Sessions table
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY CHECK(length(id) = 36),
                    persistent INTEGER NOT NULL DEFAULT {int(config.PERSISTENT_SESSIONS_DEFAULT)},
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active TEXT,
                    summary TEXT CHECK(length(summary) <= {config.SUMMARY_MAX_WORDS * 5})
                ) STRICT;
                """)

                # Messages table with timestamp default
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL CHECK(length(session_id) = 36),
                    role TEXT CHECK(role IN ({','.join(f"'{r}'" for r in config.VALID_ROLES)})),
                    content TEXT NOT NULL CHECK(length(content) <= {config.MAX_MESSAGE_LENGTH}),
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                ) STRICT;
                """)
                logging.debug("Database schema verified/created")
                
            except sqlite3.Error as e:
                logging.error(f"Database initialization failed: {str(e)}")
                raise

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Thread-safe connection pool with health checks."""
        conn = None
        try:
            with self.pool_lock:
                if self.connection_pool:
                    conn = self.connection_pool.pop()
                    try:
                        conn.execute("SELECT 1")
                        logging.debug("Reused connection from pool")
                    except sqlite3.Error:
                        conn.close()
                        conn = sqlite3.connect(self.db_path, isolation_level=None)
                        logging.debug("Created new connection (pooled was stale)")
                else:
                    conn = sqlite3.connect(self.db_path, isolation_level=None)
                    logging.debug("Created new connection (pool empty)")
                conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        except Exception as e:
            logging.error(f"Connection acquisition failed: {str(e)}")
            if conn:
                conn.close()
            raise
        finally:
            if conn:
                with self.pool_lock:
                    self.connection_pool.append(conn)
                    logging.debug("Returned connection to pool")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Atomic transaction with rollback protection."""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                logging.debug("Transaction started")
                yield conn
                conn.execute("COMMIT")
                logging.debug("Transaction committed")
            except Exception as e:
                conn.execute("ROLLBACK")
                logging.error(f"Transaction rolled back: {str(e)}")
                raise

    # === Session Management ===
    def create_session(self, session_id: str, persistent: bool) -> None:
        """Create session with timestamp auto-generation."""
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (id, persistent) VALUES (?, ?)",
                (session_id, persistent)
            )
            logging.debug(f"Created {'persistent' if persistent else 'ephemeral'} session: {session_id}")

    def is_persistent(self, session_id: str) -> bool:
        """Check session persistence status."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT persistent FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
            is_persistent = bool(result[0]) if result else False
            logging.debug(f"Session {session_id} persistence: {is_persistent}")
            return is_persistent

    # === Message Handling ===
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Save message with automatic timestamp generation."""
        with self.transaction() as conn:
            # Ensure session exists (timestamp auto-generated by DB)
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, persistent) VALUES (?, ?)",
                (session_id, config.PERSISTENT_SESSIONS_DEFAULT)
            )
            
            # Save message (timestamp handled by DEFAULT CURRENT_TIMESTAMP)
            conn.execute(
                """INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)""",
                (session_id, role, content)
            )
            
            # Update activity timestamp
            conn.execute(
                "UPDATE sessions SET last_active = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )
            logging.debug(f"Added {role} message to {session_id[:8]} (chars: {len(content)})")

    def get_messages(self, session_id: str, limit: int = config.MAX_CONTEXT_LENGTH) -> List[Message]:
        """Retrieve messages with safe timestamp handling."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT role, content, timestamp FROM messages 
                WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?""",
                (session_id, limit)
            ).fetchall()
            
            messages = []
            for row in rows:
                try:
                    # Convert timestamp only if present
                    ts = datetime.fromisoformat(row[2]) if row[2] else None
                    messages.append(Message(
                        role=row[0],
                        content=row[1],
                        timestamp=ts
                    ))
                except Exception as e:
                    logging.warning(f"Invalid timestamp format in message {row[0]}: {str(e)}")
                    messages.append(Message(
                        role=row[0],
                        content=row[1],
                        timestamp=None
                    ))
            
            logging.debug(f"Retrieved {len(messages)} messages for {session_id[:8]}")
            return list(reversed(messages))  # Return chronological order

    def get_message_count(self, session_id: str) -> int:
        """Count messages ignoring timestamp validity."""
        with self._get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,)
            ).fetchone()[0]
            logging.debug(f"Message count for {session_id[:8]}: {count}")
            return count

    # === Summarization ===
    def save_summary(self, session_id: str, summary: str) -> None:
        """Store summary with length validation."""
        if len(summary) > (config.SUMMARY_MAX_WORDS * 5):
            logging.warning(f"Summary too long ({len(summary)} chars), truncating")
            summary = summary[:config.SUMMARY_MAX_WORDS * 5]
            
        with self.transaction() as conn:
            conn.execute(
                """UPDATE sessions 
                SET summary = ?, last_active = CURRENT_TIMESTAMP 
                WHERE id = ?""",
                (summary, session_id)
            )
            logging.info(f"Saved summary for {session_id[:8]} ({len(summary)} chars)")

    def get_summary(self, session_id: str) -> Optional[str]:
        """Retrieve summary if exists."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT summary FROM sessions WHERE id = ?",
                (session_id,)
            ).fetchone()
            if result:
                logging.debug(f"Retrieved summary for {session_id[:8]}")
                return result[0]
            logging.debug(f"No summary found for {session_id[:8]}")
            return None

    def close_all(self) -> None:
        """Cleanup connections with error handling."""
        with self.pool_lock:
            for conn in self.connection_pool:
                try:
                    conn.close()
                    logging.debug("Closed database connection")
                except sqlite3.Error:
                    pass
            self.connection_pool.clear()
            logging.info("All database connections closed")