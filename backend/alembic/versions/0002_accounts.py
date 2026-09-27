"""accounts: users, sessions, codes, couples, admin events (M2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("username_norm", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=40), nullable=False),
        sa.Column("display_name_norm", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("meals_public", sa.Boolean(), nullable=False),
        sa.Column("lists_public", sa.Boolean(), nullable=False),
        sa.Column("filter_hidden", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("password_reset_by", sa.String(length=36), nullable=True),
        sa.Column("password_reset_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("language IN ('de', 'en')", name=op.f("ck_users_language")),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role")),
        sa.ForeignKeyConstraint(
            ["password_reset_by"],
            ["users.id"],
            name=op.f("fk_users_password_reset_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("display_name_norm", name=op.f("uq_users_display_name_norm")),
        sa.UniqueConstraint("username_norm", name=op.f("uq_users_username_norm")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_users_password_reset_by"), ["password_reset_by"], unique=False
        )

    op.create_table(
        "admin_events",
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_admin_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_admin_events_target_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_events")),
    )
    with op.batch_alter_table("admin_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_admin_events_actor_id"), ["actor_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_admin_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_admin_events_target_user_id"), ["target_user_id"], unique=False
        )

    op.create_table(
        "couples",
        sa.Column("requester_id", sa.String(length=36), nullable=False),
        sa.Column("addressee_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'accepted')", name=op.f("ck_couples_status")),
        sa.ForeignKeyConstraint(
            ["addressee_id"],
            ["users.id"],
            name=op.f("fk_couples_addressee_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_couples_requester_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_couples")),
    )
    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_couples_addressee_id"), ["addressee_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_couples_requester_id"), ["requester_id"], unique=False)

    op.create_table(
        "one_time_codes",
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("code_hmac", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("tailscale_share_url", sa.String(length=500), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('invite', 'reset')", name=op.f("ck_one_time_codes_kind")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_one_time_codes_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_one_time_codes_target_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["users.id"],
            name=op.f("fk_one_time_codes_used_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_codes")),
        sa.UniqueConstraint("code_hmac", name=op.f("uq_one_time_codes_code_hmac")),
    )
    with op.batch_alter_table("one_time_codes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_one_time_codes_created_by"), ["created_by"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_one_time_codes_target_user_id"), ["target_user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_one_time_codes_used_by"), ["used_by"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "couple_members",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("couple_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["couple_id"],
            ["couples.id"],
            name=op.f("fk_couple_members_couple_id_couples"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_couple_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_couple_members")),
    )
    with op.batch_alter_table("couple_members", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_couple_members_couple_id"), ["couple_id"], unique=False
        )

    op.create_table(
        "session_tokens",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("token_hmac", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("forked_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_session_tokens_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_tokens")),
        sa.UniqueConstraint("token_hmac", name=op.f("uq_session_tokens_token_hmac")),
    )
    with op.batch_alter_table("session_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_session_tokens_session_id"), ["session_id"], unique=False
        )



def downgrade() -> None:
    with op.batch_alter_table("session_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_session_tokens_session_id"))

    op.drop_table("session_tokens")
    with op.batch_alter_table("couple_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_couple_members_couple_id"))

    op.drop_table("couple_members")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))

    op.drop_table("sessions")
    with op.batch_alter_table("one_time_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_one_time_codes_used_by"))
        batch_op.drop_index(batch_op.f("ix_one_time_codes_target_user_id"))
        batch_op.drop_index(batch_op.f("ix_one_time_codes_created_by"))

    op.drop_table("one_time_codes")
    with op.batch_alter_table("couples", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_couples_requester_id"))
        batch_op.drop_index(batch_op.f("ix_couples_addressee_id"))

    op.drop_table("couples")
    with op.batch_alter_table("admin_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_admin_events_target_user_id"))
        batch_op.drop_index(batch_op.f("ix_admin_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_admin_events_actor_id"))

    op.drop_table("admin_events")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_password_reset_by"))

    op.drop_table("users")
