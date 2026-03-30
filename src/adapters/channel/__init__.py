"""Channel adapter package — provider-agnostic notification interface.

Public API:
  - ``ChannelAdapter`` ABC and ``SlackAdapter`` concrete implementation
  - Typed schemas: ``RoutingPayload``, ``DeliveryResult``, ``Destination``, etc.
  - Exception hierarchy rooted at ``ChannelAdapterError``
"""

from src.adapters.channel.base import ChannelAdapter
from src.adapters.channel.exceptions import (
    ChannelAdapterError,
    ChannelAuthError,
    ChannelConnectionError,
    ChannelDeliveryError,
    ChannelRateLimitError,
)
from src.adapters.channel.formatters import (
    PRIORITY_COLORS,
    PRIORITY_EMOJIS,
    SlackBlockKitFormatter,
)
from src.adapters.channel.schemas import (
    ChannelCredentials,
    ClassificationInfo,
    ConnectionStatus,
    ConnectionTestResult,
    DeliveryResult,
    Destination,
    RoutingPayload,
    SenderInfo,
)
from src.adapters.channel.slack import SlackAdapter

__all__ = [
    "ChannelAdapter",
    "ChannelAdapterError",
    "ChannelAuthError",
    "ChannelConnectionError",
    "ChannelCredentials",
    "ChannelDeliveryError",
    "ChannelRateLimitError",
    "ClassificationInfo",
    "ConnectionStatus",
    "ConnectionTestResult",
    "DeliveryResult",
    "Destination",
    "PRIORITY_COLORS",
    "PRIORITY_EMOJIS",
    "RoutingPayload",
    "SenderInfo",
    "SlackAdapter",
    "SlackBlockKitFormatter",
]
