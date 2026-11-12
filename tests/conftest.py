from collections.abc import Callable
from typing import Any

import pytest

from evalsentinel.catalog import CHECK_IDS, CONTROLS, Control


@pytest.fixture
def native_checks() -> Callable[[Control], list[dict[str, Any]]]:
    def make(control: Control = CONTROLS[0]) -> list[dict[str, Any]]:
        checks = []
        for check_id, status in zip(CHECK_IDS, control.expected, strict=True):
            untestable = control.polarity == "not_run" or (
                control.polarity == "bad" and check_id != control.focus and status != "SUCCESS"
            )
            checks.append({"id": check_id, "status": status, "details": {"untestable": untestable}})
        if control.polarity != "not_run":
            checks.append(
                {
                    "id": "wire-schema-valid",
                    "status": "SUCCESS",
                    "details": {
                        "messagesValidated": 10,
                        "violations": [],
                    },
                }
            )
        return checks

    return make
