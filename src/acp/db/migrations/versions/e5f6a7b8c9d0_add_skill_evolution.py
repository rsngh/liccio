"""add skill_evolution_events table (Round 18)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-04 18:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401
from alembic import op  # noqa: F401

revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'skill_evolution_events',
        sa.Column('scope_key', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('skill_evolution_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_evolution_events_scope_key'),
                              ['scope_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_skill_evolution_events_action'),
                              ['action'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('skill_evolution_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_evolution_events_action'))
        batch_op.drop_index(batch_op.f('ix_skill_evolution_events_scope_key'))
    op.drop_table('skill_evolution_events')
