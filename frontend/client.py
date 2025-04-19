import httpx
import uuid
import os
from pathlib import Path
from typing import Optional, Dict, Any
from config import (
    LLM_API_URL,
    REQUEST_TIMEOUT,
    ENABLE_TTS,
    TTS_ENGINE,
    TTS_VOICE,
    TTS_SPEED,
    TEMP_DIR,
    TTS_CACHE_TTL
)
import time
import shutil

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


class TTSEngine:
    """Handles all TTS operations with cache and cleanup"""
    def __init__(self):
        self.cache_dir = Path(TEMP_DIR)
        self._setup_engine()

    def _setup_engine(self):
        """Initialize the selected TTS engine"""
        if TTS_ENGINE == "pyttsx3":
            import pyttsx3
            self.engine = pyttsx3.init()
            if TTS_VOICE:
                self.engine.setProperty('voice', TTS_VOICE)
            self.engine.setProperty('rate', 150 * TTS_SPEED)
        elif TTS_ENGINE == "system":
            if os.name == 'nt':
                import win32com.client
                self.engine = win32com.client.Dispatch("SAPI.SpVoice")
            else:
                import pyttsx3  # Fallback for non-Windows
                self.engine = pyttsx3.init()
        else:  # gTTS
            from gtts import gTTS
            self.gTTS = gTTS

    def generate_audio(self, text: str) -> Optional[str]:
        """Convert text to speech, return audio file path"""
        if not text.strip() or not ENABLE_TTS:
            return None

        # Create cache-friendly filename
        text_hash = str(abs(hash(text)))
        audio_path = self.cache_dir / f"{text_hash}.mp3"

        # Return cached file if exists and fresh
        if audio_path.exists():
            file_age = time.time() - audio_path.stat().st_mtime
            if file_age < TTS_CACHE_TTL:
                return str(audio_path)

        try:
            if TTS_ENGINE == "gTTS":
                tts = self.gTTS(text=text, lang='en')
                tts.save(str(audio_path))
            else:
                if TTS_ENGINE == "system" and os.name == 'nt':
                    self.engine.Speak(text)  # Windows native
                    return None  # No file output
                else:  # pyttsx3 or fallback
                    self.engine.save_to_file(text, str(audio_path))
                    self.engine.runAndWait()
            return str(audio_path)
        except Exception as e:
            print(f"TTS Error: {e}")
            return None

    def cleanup(self):
        """Remove expired audio files"""
        now = time.time()
        for file in self.cache_dir.glob("*.mp3"):
            if now - file.stat().st_mtime > TTS_CACHE_TTL:
                file.unlink()


class APIClient:
    """Handles all LLM API communication"""
    def __init__(self):
        self.tts = TTSEngine() if ENABLE_TTS else None
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    async def send_to_llm(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send message to LLM API and return processed response"""
        try:
            payload = {
                "message": message,
                "session_id": session_id or str(uuid.uuid4())
            }
            
            response = await self.client.post(
                LLM_API_URL,
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            audio_path = None
            
            if self.tts and "response" in data:
                audio_path = self.tts.generate_audio(data["response"])
            
            return {
                "text": data.get("response", ""),
                "session_id": data.get("session_id", payload["session_id"]),
                "audio": audio_path
            }
            
        except httpx.HTTPStatusError as e:
            return {
                "text": f"API Error: {e.response.status_code}",
                "session_id": session_id or str(uuid.uuid4()),
                "audio": None
            }
        except Exception as e:
            return {
                "text": f"System Error: {str(e)}",
                "session_id": session_id or str(uuid.uuid4()),
                "audio": None
            }

    async def close(self):
        """Cleanup resources"""
        await self.client.aclose()
        if self.tts:
            self.tts.cleanup()


# Singleton instance for the app
api_client = APIClient()