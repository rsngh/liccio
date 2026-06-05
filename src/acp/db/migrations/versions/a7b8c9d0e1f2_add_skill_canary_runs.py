"""add skill_canary_runs table (Alpha 22 WS13)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-04 22:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'skill_canary_runs',
        sa.Column('scope_key', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('skill_canary_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_canary_runs_scope_key'),
                              ['scope_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_skill_canary_runs_status'),
                              ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('skill_canary_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_canary_runs_status'))
        batch_op.drop_index(batch_op.f('ix_skill_canary_runs_scope_key'))
    op.drop_table('skill_canary_runs')
