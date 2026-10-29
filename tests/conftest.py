import json
from pathlib import Path
from unittest.mock import patch

import pytest

import custom_components.kitaplus.api.client  # noqa: F401  (the patches below need it imported)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components in tests."""
    yield


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def fixed_account_id(request):
    """Every sign-in also reads the KitaPlus account id; tests answer it without network.

    Tests marked `real_client` talk to the client with mocked HTTP and need the real method.
    """
    if request.node.get_closest_marker("real_client"):
        yield
        return
    with patch(
        "custom_components.kitaplus.api.client.KitaPlusClient.async_get_account_id", return_value=4242
    ) as mock:
        yield mock
