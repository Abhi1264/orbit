import os

import pytest


def require_db(reason: str) -> None:
    if os.environ.get("ORBIT_INTEGRATION"):
        pytest.fail(reason)
    pytest.skip(reason)
