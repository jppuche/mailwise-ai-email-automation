"""Unit tests for timing oracle / username enumeration prevention.

Validates:
- _DUMMY_HASH is a valid bcrypt hash (starts with $2b$).
- verify_password("anything", _DUMMY_HASH) returns False (not a crash).
- verify_password with any plain text against _DUMMY_HASH always returns False.

The constant-time behaviour itself (response-time delta < epsilon) is not
asserted here — that requires statistical load testing.  These tests confirm
the structural invariants that enable constant-time operation.
"""

from __future__ import annotations

import bcrypt as _bcrypt

from src.core.security import _DUMMY_HASH, verify_password


class TestDummyHash:
    """_DUMMY_HASH structural invariants."""

    def test_is_string(self) -> None:
        assert isinstance(_DUMMY_HASH, str)

    def test_is_valid_bcrypt_hash(self) -> None:
        """bcrypt hashes start with $2b$ — any other prefix indicates a bug."""
        assert _DUMMY_HASH.startswith("$2b$"), (
            f"_DUMMY_HASH must be a bcrypt hash, got prefix: {_DUMMY_HASH[:8]!r}"
        )

    def test_bcrypt_checkpw_does_not_raise(self) -> None:
        """Calling bcrypt.checkpw against _DUMMY_HASH must not raise any exception."""
        result = _bcrypt.checkpw(b"any-password", _DUMMY_HASH.encode("utf-8"))
        assert isinstance(result, bool)

    def test_verify_password_returns_false_for_any_input(self) -> None:
        """verify_password against _DUMMY_HASH always returns False.

        The placeholder was never created from a real password, so no input
        should verify successfully.
        """
        assert verify_password("dummy-constant-time-placeholder", _DUMMY_HASH) is False
        assert verify_password("wrong-password", _DUMMY_HASH) is False
        assert verify_password("", _DUMMY_HASH) is False  # type: ignore[arg-type]

    def test_verify_password_does_not_raise_on_dummy_hash(self) -> None:
        """verify_password must complete without exception — not crash with an invalid hash."""
        try:
            verify_password("anything", _DUMMY_HASH)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"verify_password raised {type(exc).__name__} on _DUMMY_HASH: {exc}"
            ) from exc

    def test_dummy_hash_differs_from_real_hash(self) -> None:
        """_DUMMY_HASH must not accidentally match any real password."""
        from src.core.security import hash_password

        real_hash = hash_password("some-user-password")
        assert real_hash != _DUMMY_HASH

    def test_module_level_constant_is_stable(self) -> None:
        """Importing _DUMMY_HASH twice yields the same object (module-level constant)."""
        from src.core.security import _DUMMY_HASH as _DUMMY_HASH_2

        assert _DUMMY_HASH is _DUMMY_HASH_2
