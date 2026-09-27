import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import main
from app.core.errors import ErrorCode, FieldErrorCode

runner = CliRunner()


def test_export_openapi_needs_no_secret_and_is_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "a" / "openapi.json", tmp_path / "b" / "openapi.json"
    assert runner.invoke(main, ["export-openapi", str(first)]).exit_code == 0
    assert runner.invoke(main, ["export-openapi", str(second)]).exit_code == 0

    text = first.read_text(encoding="utf-8")
    assert text == second.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    document = json.loads(text)
    assert text == json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    schemas = document["components"]["schemas"]
    assert schemas["ErrorCode"]["enum"] == [code.value for code in ErrorCode]
    assert schemas["FieldErrorCode"]["enum"] == [code.value for code in FieldErrorCode]
    assert set(schemas["ErrorResponse"]["required"]) == {"code", "params", "fields"}
    assert "HTTPValidationError" not in schemas


def test_export_openapi_describes_every_operation(tmp_path: Path) -> None:
    path = tmp_path / "openapi.json"
    runner.invoke(main, ["export-openapi", str(path)])
    document = json.loads(path.read_text(encoding="utf-8"))

    operations = {
        (url, method): operation
        for url, item in document["paths"].items()
        for method, operation in item.items()
    }
    assert {op["operationId"] for op in operations.values()} == {
        "get_health",
        "get_version",
        "set_diag_cookie",
        "check_diag_cookie",
        "login",
        "refresh",
        "logout",
        "logout_all",
        "check_code",
        "join",
        "reset_password",
        "get_me",
        "update_me",
        "change_password",
        "list_sessions",
        "revoke_session",
        "get_security",
        "get_couple",
        "create_couple_request",
        "accept_couple_request",
        "decline_couple_request",
        "cancel_couple_request",
        "end_couple",
        "list_users",
        "list_visible_users",
        "admin_list_users",
        "admin_update_user",
        "admin_delete_user",
        "admin_create_reset_link",
        "admin_list_invites",
        "admin_create_invite",
        "admin_revoke_invite",
        "admin_list_events",
        "list_categories",
        "list_units",
        "list_cuisines",
        "create_cuisine",
        "list_tags",
        "list_ingredients",
        "list_similar_ingredients",
        "create_ingredient",
        "get_ingredient",
        "update_ingredient",
        "list_ingredient_products",
        "create_product",
        "get_product",
        "update_product",
        "admin_reorder_categories",
        "admin_merge_ingredient",
        "admin_delete_ingredient",
    }
    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    for operation in operations.values():
        assert operation["responses"]["default"]["content"]["application/json"]["schema"] == (
            error_ref
        )
    assert document["info"]["license"]["identifier"] == "AGPL-3.0-or-later"


def test_export_openapi_ignores_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEALMATE_VERSION", "9.9.9")
    monkeypatch.setenv("MEALMATE_COOKIE_SECURE", "false")
    path = tmp_path / "openapi.json"
    assert runner.invoke(main, ["export-openapi", str(path)]).exit_code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["info"]["version"] == "0.0.0-dev"


def test_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_VERSION", "2.0.0-rc.1")
    monkeypatch.setenv("MEALMATE_COMMIT", "0123abc")
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert result.output == "2.0.0-rc.1 (0123abc)\n"


def test_commands_need_a_valid_configuration(tmp_path: Path) -> None:
    for args in (["db", "upgrade"], ["backup-db", str(tmp_path / "copy.db")]):
        result = runner.invoke(main, args)
        assert result.exit_code == 2
        assert "Invalid configuration" in result.output
        assert "secret_key" in result.output
