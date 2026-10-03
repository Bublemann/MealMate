"""category names: a German and an English name per category (D-31)

Category names move from the frontend's translation files into the database (I18N-04), so that
adding or renaming a category only means writing data (REF-01). `categories` gains `name_de` and
`name_en`, each with its normalised form (`*_norm`, plan § 5.2), unique per language. Every
seeded key gets the names its translations `category.<key>` had when this migration was written
(requirements appendix A). The key stays. Only columns are added; no existing value changes, and
the downgrade drops them again.

`normalize` is copied from `app.domain.text` as it was when this migration was written, so that
later changes there cannot change what it does.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02 00:00:00+00:00
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAME_LENGTH = 40
NAME_NORM_LENGTH = 160
LANGUAGES = ("de", "en")
# (German, English) by key, as `frontend/src/i18n/de.json` and `en.json` had them.
NAMES = {
    "fruit_vegetables": ("Obst & Gemüse", "Fruit & vegetables"),
    "bread_bakery": ("Brot & Backwaren", "Bread & bakery"),
    "dairy_eggs": ("Milchprodukte & Eier", "Dairy & eggs"),
    "cheese": ("Käse", "Cheese"),
    "meat_fish": ("Fleisch & Fisch", "Meat & fish"),
    "sausage_deli": ("Wurst & Aufschnitt", "Sausage & deli"),
    "plant_based": ("Tofu & pflanzliche Alternativen", "Tofu & plant-based"),
    "pasta_rice_grains": ("Nudeln, Reis & Getreide", "Pasta, rice & grains"),
    "canned_jars": ("Konserven & Gläser", "Canned & jarred"),
    "sauces_spices_oils": ("Soßen, Gewürze & Öle", "Sauces, spices & oils"),
    "baking": ("Backzutaten", "Baking"),
    "breakfast_spreads": ("Frühstück & Aufstriche", "Breakfast & spreads"),
    "snacks_sweets": ("Süßes & Snacks", "Snacks & sweets"),
    "frozen": ("Tiefkühl", "Frozen"),
    "drinks": ("Getränke", "Drinks"),
    "household_hygiene": ("Drogerie & Haushalt", "Household & toiletries"),
    "other": ("Sonstiges", "Other"),
}

_GERMAN_FOLDS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize(text: str) -> str:
    """`app.domain.text.normalize` as of this revision."""
    folded = unicodedata.normalize("NFKC", text).lower().translate(_GERMAN_FOLDS)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def _fill_names(connection: sa.Connection) -> None:
    """The seeded names by key. Categories were only ever seeded, so every key has its names; a
    key without them (none is known) is named by itself, which keeps both names unique."""
    rows = connection.execute(sa.text("SELECT id, key FROM categories")).all()
    if not rows:
        return
    values = []
    for row_id, key in rows:
        name_de, name_en = NAMES.get(key, (key, key))
        values.append(
            {
                "id": row_id,
                "name_de": name_de,
                "name_de_norm": normalize(name_de),
                "name_en": name_en,
                "name_en_norm": normalize(name_en),
            }
        )
    connection.execute(
        sa.text(
            "UPDATE categories SET name_de = :name_de, name_de_norm = :name_de_norm, "
            "name_en = :name_en, name_en_norm = :name_en_norm WHERE id = :id"
        ),
        values,
    )


def upgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        for language in LANGUAGES:
            batch_op.add_column(
                sa.Column(f"name_{language}", sa.String(length=NAME_LENGTH), nullable=True)
            )
            batch_op.add_column(
                sa.Column(
                    f"name_{language}_norm", sa.String(length=NAME_NORM_LENGTH), nullable=True
                )
            )

    _fill_names(op.get_bind())

    with op.batch_alter_table("categories", schema=None) as batch_op:
        for language in LANGUAGES:
            batch_op.alter_column(
                f"name_{language}", existing_type=sa.String(length=NAME_LENGTH), nullable=False
            )
            batch_op.alter_column(
                f"name_{language}_norm",
                existing_type=sa.String(length=NAME_NORM_LENGTH),
                nullable=False,
            )
            batch_op.create_index(
                batch_op.f(f"ix_categories_name_{language}_norm"),
                [f"name_{language}_norm"],
                unique=True,
            )


def downgrade() -> None:
    with op.batch_alter_table("categories", schema=None) as batch_op:
        for language in reversed(LANGUAGES):
            batch_op.drop_index(batch_op.f(f"ix_categories_name_{language}_norm"))
            batch_op.drop_column(f"name_{language}_norm")
            batch_op.drop_column(f"name_{language}")
