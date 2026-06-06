"""add shadow_decisions table (Alpha 27 — production shadow store)

Revision ID: c9d0e1f2a3b4
Revises: a7b8c9d0e1f2
Create Date: 2026-06-06 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'c9d0e1f2a3b4'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'shadow_decisions',
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('human_verdict', sa.String(), nullable=True),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('shadow_decisions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shadow_decisions_task_id'), ['task_id'],
                              unique=False)
        batch_op.create_index(batch_op.f('ix_shadow_decisions_human_verdict'),
                              ['human_verdict'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('shadow_decisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shadow_decisions_human_verdict'))
        batch_op.drop_index(batch_op.f('ix_shadow_decisions_task_id'))
    op.drop_table('shadow_decisions')
