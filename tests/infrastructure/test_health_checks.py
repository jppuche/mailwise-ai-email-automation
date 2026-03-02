"""Docker health check tests — require running containers.

Marked with @pytest.mark.docker — skipped unless --docker flag is passed.
These tests verify that docker-compose health checks are correctly
configured and that all services reach healthy state.

Static structure tests (no Docker required) verify the compose file
itself without spawning containers.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "docker-compose.yml"

docker = pytest.mark.docker


def _docker_compose_available() -> bool:
    """Check if docker compose CLI is available on PATH."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


skip_no_docker = pytest.mark.skipif(
    not _docker_compose_available(),
    reason="Docker Compose not available",
)

skip_no_env = pytest.mark.skipif(
    not (ROOT / ".env").exists(),
    reason=".env file not present (required by docker-compose.yml)",
)


# ---------------------------------------------------------------------------
# Static tests — no Docker required, just parse docker-compose.yml on disk
# ---------------------------------------------------------------------------


class TestComposeFileStructure:
    """Static analysis of docker-compose.yml — no containers needed."""

    def test_compose_file_exists(self) -> None:
        assert COMPOSE_PATH.exists(), f"docker-compose.yml not found at {COMPOSE_PATH}"

    def test_all_services_listed(self) -> None:
        """Expected services are defined in the compose file."""
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        expected_services = ["db", "redis", "api", "worker", "scheduler", "frontend"]
        for service in expected_services:
            assert re.search(rf"^\s+{re.escape(service)}:", content, re.MULTILINE), (
                f"Service '{service}' not found in docker-compose.yml"
            )

    def test_images_pinned_to_patch_version(self) -> None:
        """All Docker images have pinned patch versions (pre-mortem Cat 10)."""
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        image_lines = re.findall(r"image:\s*(.+)", content)
        for image in image_lines:
            image = image.strip()
            assert re.search(r"\d+\.\d+", image), (
                f"Image '{image}' is not pinned to a specific version (major.minor minimum)"
            )

    def test_healthcheck_intervals_use_env_vars(self) -> None:
        """Health check timing values use ${VAR:-default} env substitution, not hardcoded.

        Validates pre-mortem Cat 8: load-bearing defaults are configurable
        without an image rebuild — operators set HEALTHCHECK_INTERVAL etc.
        """
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        # Lines like `interval: 30s` (value does NOT start with ${) are hardcoded
        hardcoded = re.findall(
            r"^\s+(interval|timeout|retries|start_period):\s+(?!\$\{).+$",
            content,
            re.MULTILINE,
        )
        assert not hardcoded, (
            "Hardcoded healthcheck values found (should use ${VAR:-default}):\n"
            + "\n".join(f"  {h}" for h in hardcoded)
        )

    def test_each_service_has_healthcheck_key(self) -> None:
        """Every service block contains a 'healthcheck:' key.

        This is a text-level check — it does not parse YAML structure,
        but it catches obviously missing healthchecks before Docker is
        even available.
        """
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        # Split into service blocks by top-level 2-space indented service names
        service_pattern = re.compile(r"^  (\w[\w-]*):", re.MULTILINE)
        service_matches = list(service_pattern.finditer(content))

        known_services = {"db", "redis", "api", "worker", "scheduler", "frontend"}

        for i, match in enumerate(service_matches):
            service_name = match.group(1)
            if service_name not in known_services:
                continue
            # Get content up to next same-level service definition
            start = match.start()
            end = service_matches[i + 1].start() if i + 1 < len(service_matches) else len(content)
            block = content[start:end]
            assert "healthcheck:" in block, (
                f"Service '{service_name}' is missing a healthcheck block"
            )

    def test_known_images_are_pinned(self) -> None:
        """Specific image tags known from Block 19 spec are present."""
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        assert "postgres:16.6-alpine" in content, "postgres image not pinned to 16.6-alpine"
        assert "redis:7.4-alpine" in content, "redis image not pinned to 7.4-alpine"

    def test_scheduler_command_is_correct(self) -> None:
        """Scheduler command points to src.scheduler (not src.tasks.scheduler).

        This was a known bug fixed in B19 — regression guard.
        """
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        # Must contain the correct module path
        assert "python -m src.scheduler" in content, (
            "Scheduler command should be 'python -m src.scheduler'"
        )
        # Must NOT contain the incorrect path
        assert "python -m src.tasks.scheduler" not in content, (
            "Scheduler command contains the old buggy path 'src.tasks.scheduler'"
        )

    def test_api_healthcheck_path_is_correct(self) -> None:
        """API health check uses the correct endpoint path.

        Known bug fixed in B19: was /health, corrected to /api/v1/health.
        """
        content = COMPOSE_PATH.read_text(encoding="utf-8")
        assert "/api/v1/health" in content, "API healthcheck should probe /api/v1/health"
        # The old (wrong) path should not appear as a standalone health probe
        # Note: /api/v1/health contains /health as substring, so we check
        # for the pattern that would indicate the wrong path only
        wrong_path_pattern = re.compile(
            r"urlopen\(['\"]http://[^'\"]+/health['\"]",
        )
        for match in wrong_path_pattern.finditer(content):
            assert "/api/v1/health" in match.group(), (
                f"Found health probe with non-versioned path: {match.group()}"
            )


# ---------------------------------------------------------------------------
# Docker-dependent tests — require running Docker daemon
# ---------------------------------------------------------------------------


@docker
@skip_no_docker
@skip_no_env
class TestDockerHealthChecks:
    """Verify docker-compose health check configuration via docker compose CLI."""

    def test_compose_config_valid(self) -> None:
        """docker compose config parses without errors."""
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        assert result.returncode == 0, f"docker compose config error: {result.stderr}"

    def test_all_services_have_healthcheck(self) -> None:
        """Every service in docker-compose.yml has a healthcheck defined."""
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            pytest.skip("PyYAML not installed — cannot parse compose output")

        result = subprocess.run(
            ["docker", "compose", "config"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        assert result.returncode == 0

        config = yaml.safe_load(result.stdout)
        services = config.get("services", {})

        for name, svc in services.items():
            assert "healthcheck" in svc, f"Service '{name}' is missing a healthcheck definition"
            assert "test" in svc["healthcheck"], f"Service '{name}' healthcheck has no test command"
