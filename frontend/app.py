import gradio as gr
import json
import os
from datetime import datetime
from config import (
    DEFAULT_SESSION_PROMPT,
    SESSION_ID_LABEL,
    TEXTBOX_LINES,
    SHOW_SESSION_ID,
    ENABLE_TTS,
    AUTOPLAY_AUDIO
)
from client import api_client

class ChatUI:
    def __init__(self):
        self.session_file = "session_cache.json"
        self.setup_ui()
        self.ui.launch()

    def load_session(self):
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    return data.get("history", []), data.get("session_id", "")
            except:
                pass
        return [], ""

    def save_session(self, history, session_id):
        with open(self.session_file, 'w') as f:
            json.dump({
                "history": history,
                "session_id": session_id,
                "last_updated": str(datetime.now())
            }, f)

    def setup_ui(self):
        with gr.Blocks(title="Kali Chat", css=self._darcula_css()) as self.ui:
            self.history_state = gr.State([])
            initial_history, initial_session_id = self.load_session()

            self.audio_player = gr.Audio(
                visible=False,
                autoplay=True,
                elem_id="tts_player"
            )

            with gr.Column(scale=9):
                self.chat_display = gr.Chatbot(
                    value=initial_history,
                    elem_id="chatbot",
                    avatar_images=(
                        "assets/user_avatar.png",
                        "assets/bot_avatar.png"
                    ),
                    height=560,
                    show_label=False,
                    type="messages"
                )

            with gr.Column(scale=1):
                with gr.Row():
                    self.user_input = gr.Textbox(
                        placeholder="Type your message...",
                        lines=1,
                        scale=9,
                        container=False,
                        show_label=False,
                        elem_id="user_input"
                    )
                    self.submit_btn = gr.Button("Send", variant="primary", elem_id="send_btn")

                with gr.Row(visible=SHOW_SESSION_ID) as self.controls_row:
                    self.session_id = gr.Textbox(
                        label=SESSION_ID_LABEL,
                        value=initial_session_id,
                        placeholder=DEFAULT_SESSION_PROMPT,
                        scale=9,
                        elem_id="session_id"
                    )
                    if ENABLE_TTS:
                        self.tts_toggle = gr.Checkbox(
                            label="Enable TTS",
                            value=AUTOPLAY_AUDIO,
                            container=False,
                            scale=1,
                            elem_id="tts_toggle"
                        )

            submit_fn = self.process_message
            self.user_input.submit(
                submit_fn,
                inputs=[self.user_input, self.session_id, self.tts_toggle, self.history_state] if ENABLE_TTS 
                       else [self.user_input, self.session_id, self.history_state],
                outputs=[self.chat_display, self.user_input, self.session_id, self.audio_player, self.history_state]
            )
            self.submit_btn.click(
                submit_fn,
                inputs=[self.user_input, self.session_id, self.tts_toggle, self.history_state] if ENABLE_TTS 
                       else [self.user_input, self.session_id, self.history_state],
                outputs=[self.chat_display, self.user_input, self.session_id, self.audio_player, self.history_state]
            )

    def _darcula_css(self):
        return """
        :root {
            --bg-color: #2b2b2b;
            --text-color: #a9b7c6;
            --primary-color: #4eade5;
            --secondary-color: #323232;
            --user-bubble: #214283;
            --bot-bubble: #38546a;
            --border-color: #3c3f41;
        }
        
        body {
            background-color: var(--bg-color) !important;
            color: var(--text-color) !important;
            font-family: 'Consolas', 'Monaco', monospace !important;
        }
        
        footer {
            display: none !important;
        }

        #tts_player {
            display: none !important;
        }
        
        [data-role="user"] {
            background: var(--user-bubble) !important;
            color: white !important;
            margin-left: auto !important;
            border-radius: 15px 15px 0 15px !important;
            max-width: 85% !important;
            padding: 12px !important;
            border: none !important;
        }
        
        [data-role="assistant"] {
            background: var(--bot-bubble) !important;
            color: white !important;
            margin-right: auto !important;
            border-radius: 15px 15px 15px 0 !important;
            max-width: 85% !important;
            padding: 12px !important;
            border: none !important;
        }
        
        #user_input {
            background-color: var(--secondary-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            width: 100% !important;
        }
        
        #user_input::placeholder {
            color: #6b6b6b !important;
        }
        
        #send_btn {
            background: var(--primary-color) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            margin-left: 10px !important;
            max-width: 85px !important;
        }
        
        #session_id, #tts_toggle {
            background-color: var(--secondary-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        
        .label {
            color: var(--text-color) !important;
        }
        """

    async def process_message(self, message: str, session_id: str, tts_enabled: bool = False, history: list = None):
        if not message.strip():
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update()

        response = await api_client.send_to_llm(message, session_id or None)

        audio_update = gr.update(value=None)
        if ENABLE_TTS and tts_enabled and response.get("audio"):
            audio_update = gr.update(
                value=response["audio"],
                autoplay=True,
                visible=False
            )

        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response["text"]}
        ]

        self.save_session(updated_history, response["session_id"])

        return (
            gr.update(value=updated_history),
            gr.update(value=""),
            gr.update(value=response["session_id"]),
            audio_update,
            updated_history
        )

if __name__ == "__main__":
    chat = ChatUI()