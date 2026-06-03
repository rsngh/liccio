"""add drift persistence tables

Revision ID: a1b2c3d4e5f6
Revises: f7a2c9d1e004
Create Date: 2026-06-02 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f7a2c9d1e004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table(name: str) -> None:
    op.create_table(name,
    sa.Column('model_name', sa.String(), nullable=False),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table(name, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f'ix_{name}_model_name'), ['model_name'],
                              unique=False)


def upgrade() -> None:
    _table('drift_reports')
    _table('model_demotion_events')
    _table('model_promotion_states')


def downgrade() -> None:
    for name in ('model_promotion_states', 'model_demotion_events', 'drift_reports'):
        with op.batch_alter_table(name, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{name}_model_name'))
        op.drop_table(name)
