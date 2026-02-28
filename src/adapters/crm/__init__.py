"""CRM adapter package — provider-agnostic CRM interface.

Public API:
  - ``CRMAdapter`` ABC and ``HubSpotAdapter`` concrete implementation
  - Typed schemas: ``Contact``, ``CreateContactData``, ``ActivityData``, etc.
  - Exception hierarchy rooted at ``CRMAdapterError``
"""

from src.adapters.crm.base import CRMAdapter
from src.adapters.crm.exceptions import (
    ContactNotFoundError,
    CRMAdapterError,
    CRMAuthError,
    CRMConnectionError,
    CRMRateLimitError,
    DuplicateContactError,
    FieldNotFoundError,
)
from src.adapters.crm.hubspot import HubSpotAdapter
from src.adapters.crm.schemas import (
    ActivityData,
    ActivityId,
    ConnectionStatus,
    ConnectionTestResult,
    Contact,
    CreateContactData,
    CreateLeadData,
    CRMCredentials,
    LeadId,
)

__all__ = [
    "ActivityData",
    "ActivityId",
    "CRMAdapter",
    "CRMAdapterError",
    "CRMAuthError",
    "CRMConnectionError",
    "CRMCredentials",
    "CRMRateLimitError",
    "ConnectionStatus",
    "ConnectionTestResult",
    "Contact",
    "ContactNotFoundError",
    "CreateContactData",
    "CreateLeadData",
    "DuplicateContactError",
    "FieldNotFoundError",
    "HubSpotAdapter",
    "LeadId",
]
