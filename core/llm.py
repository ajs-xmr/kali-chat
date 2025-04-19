import logging
import time
from typing import AsyncGenerator, List, Dict
from openai import AsyncOpenAI
from config import config
from .models import Message

logger = logging.getLogger(__name__)

class DeepSeekLLM:
    """LLM handler with minimal validation focusing on required fields."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT
        )
        self.default_params = {
            "model": config.MODELS["default"],
            "max_tokens": config.LLM_MAX_TOKENS,
            "temperature": config.LLM_TEMPERATURE
        }
        logger.info(
            f"LLM initialized | Model: {config.MODELS['default']} | "
            f"Max tokens: {config.LLM_MAX_TOKENS} | "
            f"Timeout: {config.LLM_TIMEOUT}s"
        )

    async def generate_response(
        self,
        messages: List[Dict],
        stream: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Generate response with:
        - Only basic field validation (role/content must exist)
        - No timestamp validation for any messages
        - System messages accepted as-is
        """
        try:
            start_time = time.time()
            logging.debug(
                f"Generating {'streamed ' if stream else ''}response | "
                f"Initial messages: {len(messages)}"
            )

            # Minimal validation - just check required fields exist
            validated_messages = []
            for msg in messages:
                if not isinstance(msg, dict):
                    raise ValueError("Message must be a dictionary")
                if "role" not in msg or "content" not in msg:
                    raise ValueError("Message missing required fields (role or content)")
                
                # Accept all messages as-is (no timestamp validation)
                validated_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            # Check roles
            if msg["role"] not in config.VALID_ROLES:
                raise ValueError(f"Invalid role: {msg['role']}")

            # API call with validated messages
            params = {
                **self.default_params,
                "messages": validated_messages,
                "stream": stream
            }
            
            logging.debug(
                f"API call prepared | Model: {params['model']} | "
                f"Messages: {len(validated_messages)}"
            )

            response = await self.client.chat.completions.create(**params)

            if stream:
                logging.debug("Streaming response chunks...")
                chunk_count = 0
                async for chunk in response:
                    content = chunk.choices[0].delta.content or ""
                    chunk_count += 1
                    yield content
                logging.debug(f"Stream complete | {chunk_count} chunks")
            else:
                result = response.choices[0].message.content
                logging.info(
                    f"Response generated | Tokens: {response.usage.completion_tokens} | "
                    f"Time: {time.time() - start_time:.2f}s | "
                    f"Chars: {len(result)}"
                )
                yield result

        except Exception as e:
            logging.error(
                f"LLM processing failed | Context: {len(messages)} messages | "
                f"Error: {str(e)}",
                exc_info=config.DEBUG
            )
            yield "⚠️ System temporarily unavailable. Please try again later."

    # [Rest of the methods remain exactly the same as in original version]
    async def generate_summary(self, messages: List[Dict]) -> str:
        """Generate summary with detailed quality tracking."""
        try:
            start_time = time.time()
            logger.debug(f"Starting summarization | Messages: {len(messages)}")
            
            prompt = self._build_summary_prompt(messages)
            logger.debug(f"Summary prompt: {prompt[:150]}...")  # Truncated
            
            response = await self.client.chat.completions.create(
                model=config.MODELS["summarization"],
                messages=[{"role": "user", "content": prompt}],
                temperature=config.LLAMA_TEMPERATURE,
                max_tokens=config.SUMMARY_MAX_WORDS // 3
            )
            
            summary = response.choices[0].message.content[:config.SUMMARY_MAX_WORDS]
            logger.info(
                f"Summary generated | Tokens: {response.usage.total_tokens} | "
                f"Time: {time.time() - start_time:.2f}s | "
                f"Quality: {self._estimate_quality(summary)}/5"
            )
            return summary

        except Exception as e:
            logger.error(
                f"Summarization failed | Messages: {len(messages)} | "
                f"Error: {str(e)}",
                exc_info=config.DEBUG
            )
            return "⚠️ Could not generate summary."

    async def health_check(self) -> bool:
        """Comprehensive API health probe."""
        try:
            start_time = time.time()
            logger.debug("Running LLM health check...")
            
            await self.client.chat.completions.create(
                model=config.MODELS["default"],
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=config.HEALTH_CHECK_MAX_TOKENS,
                timeout=config.HEALTH_CHECK_TIMEOUT
            )
            
            latency = time.time() - start_time
            logger.info(f"Health check passed | Latency: {latency:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False

    def _build_summary_prompt(self, messages: List[Dict]) -> str:
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
        logger.debug(f"Prompt length: {len(prompt)} chars")
        return prompt

    def _estimate_quality(self, summary: str) -> int:
        """Heuristic quality score (1-5) based on structure."""
        lines = summary.split('\n')
        bullet_points = sum(1 for line in lines if line.strip().startswith('-'))
        
        if len(summary) < 50:
            return 1
        elif bullet_points >= 3:
            return 5
        elif bullet_points >= 1:
            return 3
        return 2