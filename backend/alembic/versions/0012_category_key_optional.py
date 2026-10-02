"""category key optional: admins add categories (REF-01)

Admins add categories with a German and an English name (REF-01, ADM-01). Such a category has no
key: the key names the seeded categories, identifies *Other* and drives the Open Food Facts
guess. `categories.key` becomes nullable and stays unique among the categories that have one. No
existing value changes.

The downgrade refuses with a clear error while categories without a key exist, rather than
inventing keys for them (plan § 6): below 0009 a key is all a category has.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-02 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY_LENGTH = 40


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.alter_column("key", existing_type=sa.String(length=KEY_LENGTH), nullable=True)


class CategoriesWithoutKeyError(RuntimeError):
    """The downgrade cannot give the categories admins added a key."""


def _check_every_category_has_a_key(connection: sa.Connection) -> None:
    names = list(
        connection.execute(
            sa.text("SELECT name_en FROM categories WHERE key IS NULL ORDER BY sort_order LIMIT 10")
        ).scalars()
    )
    if names:
        raise CategoriesWithoutKeyError(
            "cannot downgrade below 0012: admins added categories, which have no key "
            f"({', '.join(repr(name) for name in names)}), but every category needs one before "
            "0012"
        )


def downgrade() -> None:
    _check_every_category_has_a_key(op.get_bind())
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.alter_column("key", existing_type=sa.String(length=KEY_LENGTH), nullable=False)
