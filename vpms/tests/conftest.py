"""VPMS test configuration — enables pytest-asyncio with auto mode."""

import pytest

# Ensure pytest-asyncio uses "auto" mode so @pytest.mark.asyncio works
# without explicit event_loop_policy configuration.
pytest_plugins = ["pytest_asyncio"]
