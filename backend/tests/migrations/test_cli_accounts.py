"""`create-admin`, `reset-link` and `seed-demo` (ACC-12, plan § 5.11)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import bcrypt
import pytest
from typer.testing import CliRunner

from app.cli import main
from app.db.migrations import upgrade_database

runner = CliRunner()
PUBLIC_URL = "https://mealmate.example.ts.net"
PASSWORD = "correct horse battery"  # noqa: S105 -- a test password


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, secret_key: str, data_dir: Path) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", secret_key)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_BCRYPT_ROUNDS", "4")
    monkeypatch.setenv("MEALMATE_PUBLIC_URL", PUBLIC_URL)


@pytest.fixture
def database(data_dir: Path) -> Path:
    upgrade_database(data_dir)
    return data_dir / "mealmate.db"


def query(database: Path, sql: str, *params: object) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(sql, params).fetchall()


def create_admin(*args: str, stdin: str = PASSWORD + "\n") -> tuple[int, str]:
    result = runner.invoke(
        main,
        [
            "create-admin",
            "--password-stdin",
            "--username",
            "admin",
            "--display-name",
            "Admin",
            *args,
        ],
        input=stdin,
    )
    return result.exit_code, result.output


def test_account_commands_need_a_migrated_database(data_dir: Path) -> None:
    for args in (["create-admin"], ["reset-link", "admin"], ["seed-demo"]):
        result = runner.invoke(main, args)
        assert result.exit_code == 1, args
        assert "run `mealmate db upgrade` first" in result.output


def test_create_admin_non_interactive(database: Path) -> None:
    code, output = create_admin("--language", "en")

    assert code == 0, output
    assert "Admin admin created." in output
    [(username, display_name, role, language, active, password_hash)] = query(
        database,
        "SELECT username, display_name, role, language, is_active, password_hash FROM users",
    )
    assert (username, display_name, role, language, active) == ("admin", "Admin", "admin", "en", 1)
    assert isinstance(password_hash, str)
    assert bcrypt.checkpw(PASSWORD.encode(), password_hash.encode())
    assert PASSWORD not in output


def test_create_admin_refuses_an_existing_username(database: Path) -> None:
    assert create_admin()[0] == 0
    code, output = create_admin()
    assert code == 1
    assert "username: taken" in output
    assert "display_name: taken" in output
    assert len(query(database, "SELECT id FROM users")) == 1


@pytest.mark.parametrize(
    ("stdin", "expected"),
    [("password\n", "password: too_common"), ("short\n", "password: too_short"), ("", "too_short")],
)
def test_create_admin_validates_like_join(database: Path, stdin: str, expected: str) -> None:
    code, output = create_admin(stdin=stdin)
    assert code == 1
    assert expected in output
    assert query(database, "SELECT id FROM users") == []


def test_create_admin_validates_the_username(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin", "--password-stdin", "--username", "Big Boss", "--display-name", "B"],
        input=PASSWORD + "\n",
    )
    assert result.exit_code == 1
    assert "username: invalid_format" in result.output


def test_password_stdin_needs_the_names(database: Path) -> None:
    result = runner.invoke(main, ["create-admin", "--password-stdin"], input=PASSWORD + "\n")
    assert result.exit_code == 2
    assert "needs --username and --display-name" in result.output


def test_create_admin_interactive(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin"],
        input=f"root\nThe Root\n{PASSWORD}\nmistyped password\n{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Username:" in result.output
    assert "Display name:" in result.output
    assert "do not match" in result.output
    assert PASSWORD not in result.output
    assert query(database, "SELECT username, display_name, role FROM users") == [
        ("root", "The Root", "admin")
    ]


def test_reset_link_reactivates_the_account(database: Path) -> None:
    create_admin()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE users SET is_active = 0")
        connection.commit()

    result = runner.invoke(main, ["reset-link", "ADMIN"])

    assert result.exit_code == 0, result.output
    url = result.output.strip()
    assert url.startswith(f"{PUBLIC_URL}/reset#")
    assert len(url.partition("#")[2]) == 43
    assert query(database, "SELECT is_active FROM users") == [(1,)]
    assert query(database, "SELECT kind, created_by FROM one_time_codes") == [("reset", None)]
    assert query(
        database, "SELECT action, actor_id, details FROM admin_events ORDER BY action"
    ) == [
        ("user.reactivate", None, '{"source": "cli"}'),
        ("user.reset_link", None, '{"source": "cli"}'),
    ]
    # A second link revokes the first; an active account is not "reactivated" again.
    assert runner.invoke(main, ["reset-link", "admin"]).exit_code == 0
    assert query(database, "SELECT count(*) FROM one_time_codes WHERE revoked_at IS NOT NULL") == [
        (1,)
    ]
    assert len(query(database, "SELECT id FROM admin_events")) == 3


def test_reset_link_for_an_unknown_user(database: Path) -> None:
    result = runner.invoke(main, ["reset-link", "nobody"])
    assert result.exit_code == 1
    assert "No user named 'nobody'" in result.output


def test_link_commands_need_the_public_url(database: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEALMATE_PUBLIC_URL")
    for args in (["reset-link", "admin"], ["seed-demo"]):
        result = runner.invoke(main, args)
        assert result.exit_code == 1
        assert "MEALMATE_PUBLIC_URL is not set" in result.output


def test_seed_demo(database: Path) -> None:
    result = runner.invoke(main, ["seed-demo"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    password = next(line for line in lines if line.startswith("Demo password")).split(": ")[1]
    invite = next(line for line in lines if line.startswith("Open invite")).split(": ")[1]
    assert invite.startswith(f"{PUBLIC_URL}/join#")
    users = dict(query(database, "SELECT username, role FROM users"))
    assert users == {"admin": "admin", "anna": "user", "ben": "user", "carl": "user"}
    [(password_hash,)] = query(database, "SELECT password_hash FROM users WHERE username = 'carl'")
    assert isinstance(password_hash, str)
    assert bcrypt.checkpw(password.encode(), password_hash.encode())
    members = query(
        database,
        "SELECT u.username FROM couple_members m JOIN users u ON u.id = m.user_id ORDER BY 1",
    )
    assert members == [("anna",), ("ben",)]
    assert query(database, "SELECT kind, used_at FROM one_time_codes") == [("invite", None)]

    again = runner.invoke(main, ["seed-demo"])
    assert again.exit_code == 1
    assert "Refusing to seed demo data" in again.output
    assert len(query(database, "SELECT id FROM users")) == 4


def test_create_admin_validates_the_display_name(database: Path) -> None:
    result = runner.invoke(
        main,
        ["create-admin", "--password-stdin", "--username", "boss", "--display-name", "  "],
        input=PASSWORD + "\n",
    )
    assert result.exit_code == 1
    assert "display_name: too_short" in result.output
