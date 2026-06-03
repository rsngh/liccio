"""add attempt_outcomes table (Round 12 WS8 — durable live evidence)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-03 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'attempt_outcomes',
        sa.Column('adapter_name', sa.String(), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('attempt_outcomes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attempt_outcomes_adapter_name'),
                              ['adapter_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_attempt_outcomes_task_type'),
                              ['task_type'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('attempt_outcomes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attempt_outcomes_task_type'))
        batch_op.drop_index(batch_op.f('ix_attempt_outcomes_adapter_name'))
    op.drop_table('attempt_outcomes')
