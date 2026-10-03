"""category deletion: deleted categories and *Uncategorized* (REF-01, D-30)

Admins delete categories (REF-01, ADM-01). A deleted category stays in the table, marked by
`deleted_at`, because lists being shopped and done lists keep showing it (D-30). Its names can
be used again, so each name stays unique only among the categories that aren't deleted: the
unique name indexes become partial. The built-in category *Uncategorized* (key
`uncategorized`, "Ohne Kategorie" / "Uncategorized") takes a deleted category's ingredients; it
is added last in the walking order. No existing value changes; a category admins added with one
of its names makes the upgrade refuse with a clear error, so that it can be renamed first.

The downgrade refuses with a clear error while deleted categories exist or ingredients are in
*Uncategorized*, rather than rewriting data (plan § 6). Otherwise it removes *Uncategorized*,
closing the gap it leaves in the order, and the column.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-03 00:00:00+00:00
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LANGUAGES = ("de", "en")
NOT_DELETED = sa.text("deleted_at IS NULL")
UNCATEGORIZED = {
    "key": "uncategorized",
    "name_de": "Ohne Kategorie",
    # The normalised names (`app.domain.text.normalize`), spelled out as migrations are frozen.
    "name_de_norm": "ohne kategorie",
    "name_en": "Uncategorized",
    "name_en_norm": "uncategorized",
}


def _name_index(language: str) -> str:
    return f"ix_categories_name_{language}_norm"


class UncategorizedNameTakenError(RuntimeError):
    """A category admins added already has one of *Uncategorized*'s names."""


def _check_the_names_are_free(connection: sa.Connection) -> None:
    names = list(
        connection.execute(
            sa.text(
                "SELECT name_en FROM categories "
                "WHERE name_de_norm = :name_de_norm OR name_en_norm = :name_en_norm"
            ),
            UNCATEGORIZED,
        ).scalars()
    )
    if names:
        raise UncategorizedNameTakenError(
            "cannot upgrade to 0013: the built-in category 'Uncategorized' (\"Ohne Kategorie\") "
            f"needs its names, but a category ({', '.join(repr(name) for name in names)}) already "
            "uses one; rename it first"
        )


def upgrade() -> None:
    _check_the_names_are_free(op.get_bind())
    op.add_column("categories", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    for language in LANGUAGES:
        op.drop_index(_name_index(language), table_name="categories")
        op.create_index(
            _name_index(language),
            "categories",
            [f"name_{language}_norm"],
            unique=True,
            sqlite_where=NOT_DELETED,
        )

    position = (
        op.get_bind()
        .execute(sa.text("SELECT coalesce(max(sort_order) + 1, 0) FROM categories"))
        .scalar_one()
    )
    # Naive UTC, as the app stores datetimes.
    now = datetime.now(UTC).replace(tzinfo=None)
    categories = sa.table(
        "categories",
        *(sa.column(name, sa.String()) for name in ("id", *UNCATEGORIZED)),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        categories,
        [
            {
                **UNCATEGORIZED,
                "id": str(uuid.uuid7()),
                "sort_order": position,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


class CategoryDeletionError(RuntimeError):
    """The downgrade cannot undo deleting categories."""


def _check_nothing_was_deleted(connection: sa.Connection) -> None:
    names = list(
        connection.execute(
            sa.text(
                "SELECT name_en FROM categories WHERE deleted_at IS NOT NULL "
                "ORDER BY sort_order LIMIT 10"
            )
        ).scalars()
    )
    if names:
        raise CategoryDeletionError(
            "cannot downgrade below 0013: admins deleted categories "
            f"({', '.join(repr(name) for name in names)}), which lists still show, but there "
            "are no deleted categories before 0013"
        )
    uncategorized = connection.execute(
        sa.text(
            "SELECT count(*) FROM ingredients JOIN categories "
            "ON categories.id = ingredients.category_id WHERE categories.key = :key"
        ),
        {"key": UNCATEGORIZED["key"]},
    ).scalar_one()
    if uncategorized:
        raise CategoryDeletionError(
            f"cannot downgrade below 0013: there are ingredients in 'Uncategorized' "
            f"({uncategorized}), which doesn't exist before 0013; give them another category first"
        )


def downgrade() -> None:
    connection = op.get_bind()
    _check_nothing_was_deleted(connection)
    position = connection.execute(
        sa.text("SELECT sort_order FROM categories WHERE key = :key"), {"key": UNCATEGORIZED["key"]}
    ).scalar_one_or_none()
    if position is not None:
        connection.execute(
            sa.text("DELETE FROM categories WHERE key = :key"), {"key": UNCATEGORIZED["key"]}
        )
        connection.execute(
            sa.text(
                "UPDATE categories SET sort_order = sort_order - 1 WHERE sort_order > :position"
            ),
            {"position": position},
        )
    for language in LANGUAGES:
        op.drop_index(_name_index(language), table_name="categories")
        op.create_index(_name_index(language), "categories", [f"name_{language}_norm"], unique=True)
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
