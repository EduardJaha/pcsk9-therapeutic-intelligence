"""Persist frozen evaluation protocols and evaluations of existing models."""
from alembic import op
import sqlalchemy as sa
revision = 'c28a4b31e712'
down_revision = 'b17f3a20d601'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evaluation_protocols', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('dataset_version_id', sa.Integer(), sa.ForeignKey('dataset_versions.id'), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('manifest_sha256', sa.String(64), unique=True, nullable=False),
                    sa.Column('protocol_json', sa.JSON(), nullable=False))
    with op.batch_alter_table('experiments') as batch:
        batch.add_column(sa.Column('protocol_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_experiment_protocol', 'evaluation_protocols', ['protocol_id'], ['id'])
    op.create_table('external_evaluations', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('experiment_id', sa.Integer(), sa.ForeignKey('experiments.id'), nullable=False),
                    sa.Column('dataset_version_id', sa.Integer(), sa.ForeignKey('dataset_versions.id'), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('results_json', sa.JSON(), nullable=False))


def downgrade():
    op.drop_table('external_evaluations')
    with op.batch_alter_table('experiments') as batch:
        batch.drop_constraint('fk_experiment_protocol', type_='foreignkey')
        batch.drop_column('protocol_id')
    op.drop_table('evaluation_protocols')
