"""Preserve discovery model manifests and research runs independently of assays."""
from alembic import op
import sqlalchemy as sa

revision = 'f51d7a64b208'
down_revision = 'e40c6d53a934'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('discovery_models', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('manifest_sha256', sa.String(64), nullable=False, unique=True),
                    sa.Column('manifest_json', sa.JSON(), nullable=False))
    op.create_table('discovery_runs', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
                    sa.Column('model_id', sa.Integer(), sa.ForeignKey('discovery_models.id'), nullable=True),
                    sa.Column('kind', sa.String(40), nullable=False), sa.Column('status', sa.String(20), nullable=False),
                    sa.Column('input_json', sa.JSON(), nullable=False), sa.Column('input_sha256', sa.String(64), nullable=False),
                    sa.Column('result_json', sa.JSON(), nullable=True), sa.Column('result_sha256', sa.String(64), nullable=True),
                    sa.Column('error', sa.Text(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_discovery_project_created', 'discovery_runs', ['project_id', 'created_at'])


def downgrade():
    op.drop_index('ix_discovery_project_created', table_name='discovery_runs')
    op.drop_table('discovery_runs')
    op.drop_table('discovery_models')
