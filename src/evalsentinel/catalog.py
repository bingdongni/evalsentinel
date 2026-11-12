"""Known-answer controls from the pagination experiment, independent of native grading."""

from dataclasses import dataclass
from typing import Literal

type Polarity = Literal["good", "bad", "not_run"]

EMPTY = "pagination-empty-cursor"
OPAQUE = "pagination-opaque-cursor"
TOOL = "pagination-tool-discovered"
END = "pagination-stops-at-end"
CHECK_IDS = (EMPTY, OPAQUE, TOOL, END)
VERSIONS = ("2025-11-25", "2026-07-28")
MCP_PIN = "c69c46dbef3083ab4e87b06a6b0e066cc487e214"
SPEC = "https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination"
PASS = ("SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS")


@dataclass(frozen=True)
class Control:
    id: str
    polarity: Polarity
    expected: tuple[str, str, str, str]
    expected_exit: int
    focus: str | None
    rationale: str


CONTROLS = (
    Control(
        "good",
        "good",
        PASS,
        0,
        None,
        "Preserve both cursors, complete the traversal, then call the last-page tool.",
    ),
    Control(
        "truthy-cursor",
        "bad",
        ("FAILURE", "FAILURE", "FAILURE", "WARNING"),
        1,
        EMPTY,
        "An empty-string cursor is valid; truthiness stops the traversal too early.",
    ),
    Control(
        "trim-cursor",
        "bad",
        ("SUCCESS", "FAILURE", "FAILURE", "WARNING"),
        1,
        OPAQUE,
        "Trimming the advertised cursor changes an opaque value.",
    ),
    Control(
        "recover-trim",
        "bad",
        ("SUCCESS", "FAILURE", "SUCCESS", "SUCCESS"),
        1,
        OPAQUE,
        "A successful retry does not erase the preceding cursor modification.",
    ),
    Control(
        "empty-page",
        "bad",
        ("SUCCESS", "FAILURE", "FAILURE", "WARNING"),
        1,
        OPAQUE,
        "An empty page with a continuation cursor is not the end of results.",
    ),
    Control(
        "past-end",
        "bad",
        ("SUCCESS", "SUCCESS", "SUCCESS", "WARNING"),
        1,
        END,
        "The same traversal continues after its terminal page; SHOULD maps to WARNING.",
    ),
    Control(
        "inert",
        "not_run",
        ("FAILURE", "FAILURE", "FAILURE", "WARNING"),
        1,
        None,
        "No requests: unexercised checks must remain visible and cannot count as catches.",
    ),
    Control(
        "rediscover",
        "good",
        PASS,
        0,
        None,
        "A fresh discovery after completing the task is a legitimate positive control.",
    ),
)
