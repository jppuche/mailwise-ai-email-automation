"""User model.

Two roles: ADMIN (full access) and REVIEWER (review queue + draft approval).
Roles are stored as a PostgreSQL ENUM type and as JWT claims for stateless auth.

password_hash stores the bcrypt hash — never the plaintext password.
Bcrypt rounds are configurable via Settings.bcrypt_rounds (default: 12).
"""

import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class UserRole(StrEnum):
    """Access role for mailwise users.

    ADMIN: full system access — manage rules, categories, users, view all emails.
    REVIEWER: access to review queue and draft approval — read-only for other data.
    """

    ADMIN = "admin"
    REVIEWER = "reviewer"


class User(Base, TimestampMixin):
    """Authenticated user with role-based access control.

    username is unique and indexed for login lookup.
    password_hash must be set via passlib[bcrypt] — never store plaintext.
    is_active=False disables login without deleting the account (soft disable).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="userrole", create_type=True),
        nullable=False,
        default=UserRole.REVIEWER,
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
