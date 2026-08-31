"""Upgrade guide candidates into a structured guide library.

Revision ID: 0010_guide_library
Revises: 0009_external_tools
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_guide_library"
down_revision: str | None = "0009_external_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("guide_candidates") as batch:
        batch.add_column(sa.Column("external_id_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("access_token_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("source_query_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("city_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("content_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("images_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("comments_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("metadata_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("user_notes_ciphertext", sa.LargeBinary(), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="discovered")
        )
        batch.add_column(sa.Column("pinned", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("detail_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index(
            "ix_guide_candidates_owner_status_pinned",
            ["owner_user_id", "status", "pinned", "updated_at"],
        )

    op.create_table(
        "conversation_message_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(40), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_artifacts_message",
        "conversation_message_artifacts",
        ["message_id", "created_at"],
    )
    op.create_table(
        "place_knowledge_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(24), nullable=False),
        sa.Column("name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("city_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("address_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("intro_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("details_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "identity_hash", name="uq_place_knowledge_identity"),
    )
    op.create_index(
        "ix_place_knowledge_owner_updated",
        "place_knowledge_cards",
        ["owner_user_id", "updated_at"],
    )
    op.create_table(
        "place_knowledge_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "card_id",
            sa.String(36),
            sa.ForeignKey("place_knowledge_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("snapshot_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("card_id", "version", name="uq_place_knowledge_revision"),
    )
    op.create_table(
        "image_analysis_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("image_identity_hash", sa.String(64), nullable=False),
        sa.Column("source_url_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("analysis_mode", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("error_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "owner_user_id",
            "image_identity_hash",
            "model_name",
            "prompt_version",
            name="uq_image_analysis_identity",
        ),
    )
    op.create_index(
        "ix_image_analysis_owner_created",
        "image_analysis_records",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("image_analysis_records")
    op.drop_table("place_knowledge_revisions")
    op.drop_table("place_knowledge_cards")
    op.drop_table("conversation_message_artifacts")
    with op.batch_alter_table("guide_candidates") as batch:
        batch.drop_index("ix_guide_candidates_owner_status_pinned")
        for column in (
            "updated_at",
            "detail_expires_at",
            "detail_fetched_at",
            "pinned",
            "status",
            "user_notes_ciphertext",
            "metadata_ciphertext",
            "comments_ciphertext",
            "images_ciphertext",
            "content_ciphertext",
            "city_ciphertext",
            "source_query_ciphertext",
            "access_token_ciphertext",
            "external_id_ciphertext",
        ):
            batch.drop_column(column)
