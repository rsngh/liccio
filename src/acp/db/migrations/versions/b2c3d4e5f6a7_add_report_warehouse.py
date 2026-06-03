"""add report warehouse tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-02 15:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('reports',
    sa.Column('kind', sa.String(), nullable=True),
    sa.Column('ingest_id', sa.String(), nullable=True),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reports_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_reports_ingest_id'), ['ingest_id'],
                              unique=False)
    op.create_table('report_lineages',
    sa.Column('report_id', sa.String(), nullable=False),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('report_lineages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_report_lineages_report_id'),
                              ['report_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('report_lineages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_report_lineages_report_id'))
    op.drop_table('report_lineages')
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reports_ingest_id'))
        batch_op.drop_index(batch_op.f('ix_reports_kind'))
    op.drop_table('reports')
