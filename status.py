"""Task status constants and state machine."""

# Task-level workflow states
BACKLOG = "BACKLOG"
READY = "READY"
IN_PROGRESS = "IN_PROGRESS"
BLOCKED = "BLOCKED"
REVIEW = "REVIEW"
QA = "QA"
DONE = "DONE"
FAILED = "FAILED"
RETRYING = "RETRYING"

# All valid states
ALL_STATES = {BACKLOG, READY, IN_PROGRESS, BLOCKED, REVIEW, QA, DONE, FAILED, RETRYING}

# Allowed transitions: from_state -> [valid next states]
VALID_TRANSITIONS = {
    BACKLOG: [READY],
    READY: [IN_PROGRESS, BLOCKED],
    IN_PROGRESS: [REVIEW, BLOCKED, FAILED, RETRYING],
    BLOCKED: [READY, IN_PROGRESS],
    REVIEW: [QA, IN_PROGRESS, FAILED],
    QA: [DONE, IN_PROGRESS, FAILED],
    DONE: [],
    FAILED: [IN_PROGRESS, RETRYING],
    RETRYING: [IN_PROGRESS, FAILED],
}


def validate_transition(from_status: str, to_status: str) -> bool:
    """Check if state transition is valid."""
    if from_status not in ALL_STATES:
        return False
    if to_status not in ALL_STATES:
        return False
    return to_status in VALID_TRANSITIONS.get(from_status, [])


def next_status(current: str) -> str | None:
    """Get next status in happy path."""
    return {
        BACKLOG: READY,
        READY: IN_PROGRESS,
        IN_PROGRESS: REVIEW,
        REVIEW: QA,
        QA: DONE,
    }.get(current)
