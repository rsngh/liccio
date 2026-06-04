"""add skill_provenance_runs table (Alpha 21 WS3)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-04 20:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'skill_provenance_runs',
        sa.Column('scope_key', sa.String(), nullable=False),
        sa.Column('skill_name', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('skill_provenance_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_provenance_runs_scope_key'),
                              ['scope_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_skill_provenance_runs_skill_name'),
                              ['skill_name'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('skill_provenance_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_provenance_runs_skill_name'))
        batch_op.drop_index(batch_op.f('ix_skill_provenance_runs_scope_key'))
    op.drop_table('skill_provenance_runs')
