"""Domain exceptions for mailwise.

These exceptions represent business logic violations, not infrastructure errors.
Infrastructure errors (DB connection, network) propagate as their own types.
"""


class InvalidStateTransitionError(Exception):
    """Raised when an email state transition violates the state machine.

    This is a logic bug, not an operational error — callers MUST NOT catch it
    in a try/except block. It indicates programmer error: the calling code
    attempted an illegal state transition.

    See VALID_TRANSITIONS in src/models/email.py for the complete state graph.
    """


class CategoryNotFoundError(Exception):
    """Raised when a required classification category does not exist in the DB."""


class DuplicateEmailError(Exception):
    """Raised when attempting to ingest an email with a provider_message_id already present."""


class AuthenticationError(Exception):
    """Raised when authentication fails: invalid credentials, expired token, etc.

    Callers: security.py (token verification), deps.py (bearer extraction).
    HTTP mapping: 401 Unauthorized (mapped in exception_handlers at app level).
    """


class AuthorizationError(Exception):
    """Raised when an authenticated user lacks permission for the requested action.

    Callers: deps.py (require_admin, require_reviewer_or_admin).
    HTTP mapping: 403 Forbidden.
    """


class NotFoundError(Exception):
    """Raised when a requested resource does not exist.
    HTTP mapping: 404 Not Found.
    """


class DuplicateResourceError(Exception):
    """Raised when a create operation violates a uniqueness constraint.
    HTTP mapping: 409 Conflict.
    """


class CategoryInUseError(Exception):
    """Raised when attempting to delete a category referenced by classifications.

    HTTP mapping: 409 Conflict with affected_email_count in body.
    Callers: CategoryService.delete_action_category / delete_type_category.
    """

    def __init__(self, category_id: object, affected_email_count: int) -> None:
        self.category_id = category_id
        self.affected_email_count = affected_email_count
        super().__init__(
            f"Cannot delete category {category_id}: "
            f"{affected_email_count} classifications reference it"
        )
