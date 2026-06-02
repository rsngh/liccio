"""add viability_assessments

Revision ID: f7a2c9d1e004
Revises: c85110947d6c
Create Date: 2026-06-02 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = 'f7a2c9d1e004'
down_revision: str | None = 'c85110947d6c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('viability_assessments',
    sa.Column('task_id', sa.String(), nullable=False),
    sa.Column('repo_id', sa.String(), nullable=True),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('viability_assessments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_viability_assessments_repo_id'), ['repo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_viability_assessments_task_id'), ['task_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('viability_assessments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_viability_assessments_task_id'))
        batch_op.drop_index(batch_op.f('ix_viability_assessments_repo_id'))

    op.drop_table('viability_assessments')
