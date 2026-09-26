"""Hatch build hook: ship the Alembic migrations inside standard (non-editable) wheels.

In the source tree `alembic.ini` and `alembic/` sit next to the `app` package. An installed
wheel has no source tree around it, so the same two paths are placed inside the package;
`app.db.migrations` looks in both places.
"""

from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class MigrationsBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "standard":
            build_data["force_include"]["alembic.ini"] = "app/alembic.ini"
            build_data["force_include"]["alembic"] = "app/alembic"
