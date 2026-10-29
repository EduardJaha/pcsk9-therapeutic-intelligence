"""Append-only literature evidence, separate from approved measurements."""
from alembic import op
import sqlalchemy as sa

revision = 'a62e8b75c319'
down_revision = 'f51d7a64b208'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('literature_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('literature_records.id'), nullable=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.Column('content_blob', sa.LargeBinary(), nullable=True),
        sa.Column('content_sha256', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_literature_project_kind', 'literature_records', ['project_id', 'kind'])


def downgrade():
    op.drop_index('ix_literature_project_kind', table_name='literature_records')
    op.drop_table('literature_records')
