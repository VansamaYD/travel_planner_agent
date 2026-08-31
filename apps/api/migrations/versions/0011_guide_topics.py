"""Store extracted guide topic tags separately from guide content.

Revision ID: 0011_guide_topics
Revises: 0010_guide_library
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_guide_topics"
down_revision: str | None = "0010_guide_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("guide_candidates") as batch:
        batch.add_column(sa.Column("tags_ciphertext", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("guide_candidates") as batch:
        batch.drop_column("tags_ciphertext")
