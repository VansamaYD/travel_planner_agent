"""Create the Slice 0 schema baseline.

Revision ID: 0001_slice0
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

revision: str = "0001_slice0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the initial migration boundary; domain tables start in Slice 1."""


def downgrade() -> None:
    """The baseline contains no domain tables."""
