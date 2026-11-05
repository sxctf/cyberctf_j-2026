from typing import Optional

class GigaChatException(Exception):
    """Base exception for GigaChat SDK"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class AuthenticationError(GigaChatException):
    """Raised when authentication fails"""

class RateLimitError(GigaChatException):
    """Raised when API rate limit is exceeded (HTTP 429)"""

class BadRequestError(GigaChatException):
    """Raised when request is malformed (HTTP 400)"""

class ForbiddenError(GigaChatException):
    """Raised when access is denied (HTTP 403)"""

class NotFoundError(GigaChatException):
    """Raised when resource is not found (HTTP 404)"""

class ServerError(GigaChatException):
    """Raised when server returns 5xx error"""
