"""add skill_documents table (Alpha 15 WS2 — skill registry)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-04 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'skill_documents',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('scope_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('skill_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_documents_name'), ['name'],
                              unique=False)
        batch_op.create_index(batch_op.f('ix_skill_documents_scope_key'), ['scope_key'],
                              unique=False)
        batch_op.create_index(batch_op.f('ix_skill_documents_status'), ['status'],
                              unique=False)


def downgrade() -> None:
    with op.batch_alter_table('skill_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_documents_status'))
        batch_op.drop_index(batch_op.f('ix_skill_documents_scope_key'))
        batch_op.drop_index(batch_op.f('ix_skill_documents_name'))
    op.drop_table('skill_documents')
