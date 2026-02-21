"""Shared test configuration — applies to all test directories.

Integration marker and --run-integration flag are defined here so they
work across tests/models/, tests/unit/, tests/integration/, etc.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require real PostgreSQL/Redis",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring real PostgreSQL/Redis",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Requires infrastructure — run with --run-integration"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
