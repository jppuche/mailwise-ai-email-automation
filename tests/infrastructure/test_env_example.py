"""Parity test: .env.example must document all Settings fields.

Parses Settings class fields and verifies each appears in .env.example
as either a variable assignment or a comment. Catches drift when new
Settings fields are added without updating .env.example.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "src" / "core" / "config.py"
ENV_EXAMPLE_PATH = ROOT / ".env.example"


def _extract_settings_fields() -> list[str]:
    """Parse Settings class and return field names as UPPER env var names."""
    source = CONFIG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fields: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id.upper())
    return fields


def _extract_env_example_vars() -> set[str]:
    """Extract variable names and commented variable names from .env.example."""
    content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    # Match lines like: VAR_NAME=value or # VAR_NAME=value or # VAR_NAME
    pattern = re.compile(r"^#?\s*([A-Z][A-Z0-9_]+?)(?:\s*=|$)", re.MULTILINE)
    return {m.group(1) for m in pattern.finditer(content)}


# Fields that are in Settings but intentionally NOT in .env.example
# (e.g., model_config is a Pydantic internal, not an env var)
_EXCLUDED = {"MODEL_CONFIG"}


class TestEnvExampleParity:
    """Every Settings field must appear in .env.example."""

    def test_all_settings_fields_documented(self) -> None:
        settings_fields = _extract_settings_fields()
        env_vars = _extract_env_example_vars()

        missing = [f for f in settings_fields if f not in env_vars and f not in _EXCLUDED]

        assert not missing, "Settings fields missing from .env.example:\n" + "\n".join(
            f"  - {f}" for f in sorted(missing)
        )

    def test_env_example_file_exists(self) -> None:
        assert ENV_EXAMPLE_PATH.exists(), ".env.example not found at project root"

    def test_config_file_exists(self) -> None:
        assert CONFIG_PATH.exists(), "src/core/config.py not found"

    def test_settings_fields_are_detected(self) -> None:
        """Smoke test: AST extraction returns a non-empty list of fields."""
        fields = _extract_settings_fields()
        assert len(fields) > 10, (
            f"Expected many Settings fields, got {len(fields)} — AST parsing may be broken"
        )

    def test_env_example_vars_are_detected(self) -> None:
        """Smoke test: regex extraction returns a non-empty set of vars."""
        env_vars = _extract_env_example_vars()
        assert len(env_vars) > 10, (
            f"Expected many .env.example vars, got {len(env_vars)} — regex may be broken"
        )

    def test_required_fields_present_in_env_example(self) -> None:
        """Required (no-default) fields must be explicitly present."""
        env_vars = _extract_env_example_vars()
        required = ["DATABASE_URL", "DATABASE_URL_SYNC", "JWT_SECRET_KEY"]
        missing = [f for f in required if f not in env_vars]
        assert not missing, f"Required fields missing from .env.example: {missing}"
