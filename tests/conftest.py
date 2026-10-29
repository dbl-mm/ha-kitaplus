import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in tests."""
    yield


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())
