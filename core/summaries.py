import logging
import time
from typing import List, Dict, AsyncGenerator
from openai import AsyncOpenAI
from config import config

logger = logging.getLogger(__name__)

class SummaryService:
    """Enhanced conversation summarization with detailed observability."""

    def __init__(self, db):
        self.db = db
        self.client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT  # Consistent with llm.py
        )
        self.model = config.MODELS["summarization"]
        logger.info(
            f"SummaryService initialized | Model: {self.model} | "
            f"Max words: {config.SUMMARY_MAX_WORDS}"
        )

    async def generate_summary(self, messages: List[Dict]) -> str:
        """
        Generate summary with:
        - Timing metrics
        - Token tracking
        - Quality validation
        """
        try:
            start_time = time.time()
            logger.debug(
                f"Starting summarization | Messages: {len(messages)} | "
                f"Approx. words: {sum(len(m['content'].split()) for m in messages)}"
            )

            prompt = self._build_prompt(messages)
            logger.debug(f"Prompt (truncated): {prompt[:150]}...")  # Avoid log spam

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config.LLAMA_TEMPERATURE,
                max_tokens=config.SUMMARY_MAX_WORDS // config.SUMMARY_TOKEN_RATIO,
                timeout=config.LLM_TIMEOUT  # Consistent timeout
            )

            summary = response.choices[0].message.content
            elapsed = time.time() - start_time

            logger.info(
                f"Summary generated | Tokens: {response.usage.total_tokens} | "
                f"Time: {elapsed:.2f}s | "
                f"Quality: {self._estimate_quality(summary)}/5"
            )
            
            return summary[:config.SUMMARY_MAX_WORDS]  # Hard truncate

        except Exception as e:
            logger.error(
                f"Summarization failed | Messages: {len(messages)} | "
                f"Error: {str(e)}",
                exc_info=config.DEBUG
            )
            return "⚠️ Summary unavailable"

    def _build_prompt(self, messages: List[Dict]) -> str:
        """Construct prompt with length validation."""
        conversation = "\n".join(
            f"{msg['role']}: {msg['content'][:config.MAX_MESSAGE_LENGTH]}"  # Truncate long messages
            for msg in messages
        )
        prompt = f"""
        {config.PROMPTS["summarization"]}
        
        Conversation:
        {conversation}
        """
        logger.debug(f"Final prompt length: {len(prompt)} chars")
        return prompt

def _estimate_quality(self, summary: str) -> int:
    """
    Calculate summary quality score (1-5) using configurable thresholds.
    Scoring logic:
    1: Empty or very short (< min_length)
    2: Plain text meeting minimum length
    3: Basic bullet points (1-2 items)
    5: Well-structured with multiple bullet points (≥ bullet_threshold)
    """
    if not summary.strip():
        return 1
        
    lines = [line.strip() for line in summary.split('\n') if line.strip()]
    has_bullets = any(line.startswith(('-', '*', '•')) for line in lines)
    
    # Use config thresholds with fallbacks
    min_length = getattr(config, 'SUMMARY_QUALITY_THRESHOLDS', {}).get('min_length', 100)
    bullet_threshold = getattr(config, 'SUMMARY_QUALITY_THRESHOLDS', {}).get('bullet_points', 3)
    
    if not lines:
        return 1
    elif has_bullets:
        return 5 if len(lines) >= bullet_threshold else 3
    else:
        return 2 if len(summary) > min_length else 1