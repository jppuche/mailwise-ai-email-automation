"""Email adapter package — provider-agnostic email interface.

Public API:
  - ``EmailAdapter`` ABC and ``GmailAdapter`` concrete implementation
  - Typed schemas: ``EmailMessage``, ``EmailCredentials``, etc.
  - Exception hierarchy rooted at ``EmailAdapterError``
"""

from src.adapters.email.base import EmailAdapter
from src.adapters.email.exceptions import (
    AuthError,
    DraftCreationError,
    EmailAdapterError,
    EmailConnectionError,
    FetchError,
    LabelError,
    RateLimitError,
)
from src.adapters.email.gmail import GmailAdapter
from src.adapters.email.schemas import (
    AttachmentData,
    ConnectionStatus,
    ConnectionTestResult,
    DraftId,
    EmailCredentials,
    EmailMessage,
    Label,
    RecipientData,
)

__all__ = [
    "AttachmentData",
    "AuthError",
    "ConnectionStatus",
    "ConnectionTestResult",
    "DraftCreationError",
    "DraftId",
    "EmailAdapter",
    "EmailAdapterError",
    "EmailConnectionError",
    "EmailCredentials",
    "EmailMessage",
    "FetchError",
    "GmailAdapter",
    "Label",
    "LabelError",
    "RateLimitError",
    "RecipientData",
]
