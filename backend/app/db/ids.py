"""Primary keys are UUIDv7 strings: unique without coordination and roughly time-ordered."""

import uuid


def new_id() -> str:
    return str(uuid.uuid7())
