import logging
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, validator, ValidationError
from config import config

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    """
    Validated chat request payload with enhanced debug logging.
    """
    message: str = Field(
        ...,
        min_length=1,
        max_length=config.MAX_MESSAGE_LENGTH,
        description=f"Message content (1-{config.MAX_MESSAGE_LENGTH} chars)"
    )
    session_id: Optional[str] = Field(
        None,
        min_length=36,
        max_length=36,
        description="UUID for persistent sessions"
    )
    stream: bool = Field(
        default=False,
        description="Enable streaming response"
    )

    @validator('session_id')
    def validate_session_id(cls, v):
        if v and not all(c in '0123456789abcdef-' for c in v.lower()):
            logger.warning(f"Invalid session ID format: {v}")
            raise ValueError("Invalid session ID format")
        return v

    @validator('message')
    def validate_message_length(cls, v):
        if len(v) > config.MAX_MESSAGE_LENGTH:
            logger.warning(
                f"Message length exceeded: {len(v)} > {config.MAX_MESSAGE_LENGTH} | "
                f"Truncated to {config.MAX_MESSAGE_LENGTH}"
            )
            v = v[:config.MAX_MESSAGE_LENGTH]
        return v

class ChatResponse(BaseModel):
    """
    Standard API response with debug metadata.
    """
    response: str
    session_id: str
    context_length: int = Field(
        ge=0,
        description="Number of messages used in context"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Response generation time"
    )

    def __init__(self, **data):
        super().__init__(**data)
        logger.debug(
            f"Response prepared | Session: {self.session_id[:8]}... | "
            f"Context: {self.context_length} messages | "
            f"Response length: {len(self.response)} chars"
        )

class Message(BaseModel):
    """
    Validated chat message with role enforcement.
    """
    role: Literal[*config.VALID_ROLES] = Field(
        ...,
        description=f"Must be one of: {', '.join(config.VALID_ROLES)}"
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=config.MAX_MESSAGE_LENGTH,
        description=f"Message text (1-{config.MAX_MESSAGE_LENGTH} chars)"
    )
    timestamp: Optional[datetime] = Field(default=None)

    @classmethod
    def validate_role(cls, v):
        if v not in config.VALID_ROLES:
            logger.error(f"Invalid role: {v} | Allowed: {config.VALID_ROLES}")
        return v

class MessageHistory(BaseModel):
    """
    Chat history response with validation logging.
    """
    messages: list[Message] = Field(
        ...,
        max_items=config.MAX_CONTEXT_LENGTH,
        description=f"Last {config.MAX_CONTEXT_LENGTH} messages"
    )
    summary: Optional[str] = Field(
        None,
        max_length=config.SUMMARY_MAX_WORDS,
        description=f"Summary (max {config.SUMMARY_MAX_WORDS} words)"
    )

    @validator('messages')
    def validate_message_count(cls, v):
        if len(v) > config.MAX_CONTEXT_LENGTH:
            logger.warning(
                f"Truncated {len(v)} messages to {config.MAX_CONTEXT_LENGTH} "
                f"(config.MAX_CONTEXT_LENGTH)"
            )
            v = v[:config.MAX_CONTEXT_LENGTH]
        return v

class ErrorResponse(BaseModel):
    """
    Standard error format with debug context.
    """
    error: str = Field(
        ...,
        description="Error type classification"
    )
    details: Optional[str] = Field(
        None,
        description="Technical details for debugging"
    )
    code: int = Field(
        ...,
        description="HTTP status code",
        examples=[400, 422, 500]
    )
    allowed_values: Optional[dict] = Field(
        None,
        description="Valid input constraints when applicable"
    )

    def log_error(self):
        logger.error(
            f"API Error {self.code}: {self.error} | "
            f"Details: {self.details or 'None'} | "
            f"Allowed values: {self.allowed_values or 'None'}"
        )

# Enhanced validation decorator
def log_validation_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            logger.error(
                f"Validation failed: {str(e)} | "
                f"Input: {kwargs if kwargs else args}",
                exc_info=config.DEBUG
            )
            raise
    return wrapper