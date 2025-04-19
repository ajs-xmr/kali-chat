# Core API Configuration
LLM_API_URL = "http://localhost:8000/chat"  # Your existing LLM API endpoint
REQUEST_TIMEOUT = 30  # Seconds before HTTP calls fail

# Session Behavior
DEFAULT_SESSION_PROMPT = "Paste Session ID (blank for new)"
SESSION_ID_LABEL = "Session ID:"

# Text-to-Speech (TTS) Settings
ENABLE_TTS = True  # Set False to disable audio completely
TTS_ENGINE = "gTTS"  # Options: "system" (OS built-in), "gTTS" (Google), "pyttsx3" (offline)

# gTTS Configuration
TTS_VOICE = {
    "language": "en",       # Primary language code (e.g., 'en', 'es', 'fr')
    "accent": "com",        # Domain for accent: 'com' (US), 'co.uk' (UK), 'com.au' (AU)
    "speed": "normal"       # 'normal' or 'slow'
}

TTS_SPEED = 1.0  # 1.0 = normal speed, 0.5-2.0 supported by most engines

# UI Defaults
TEXTBOX_LINES = 4  # Height of user input box
AUTOPLAY_AUDIO = False  # Play TTS automatically (False requires play button)
SHOW_SESSION_ID = True  # Display session ID field (False hides it)

# System TTL (Time-To-Live) Settings
TTS_CACHE_TTL = 300  # Seconds to keep generated audio files (5min)
TEMP_DIR = "./tmp_audio"  # Where to store TTS files (auto-created)