"""Add compound material identity, staged registration, assays and saved views."""
from alembic import op
import sqlalchemy as sa

revision = 'e40c6d53a934'
down_revision = 'd39b5c42f823'
branch_labels = None
depends_on = None


def identity():
    return sa.Column('id', sa.Integer(), primary_key=True)


def created():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)


def ref(name, target):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target), nullable=False)


def text(name, size=None):
    return sa.Column(name, sa.String(size) if size else sa.Text(), nullable=False)


def upgrade():
    op.create_table('registered_compounds', identity(), ref('project_id', 'projects.id'),
                    text('name', 120), text('input_smiles'), text('canonical_smiles'), text('structure_sha256', 64),
                    text('modality', 40), text('source_reference'), text('notes'),
                    sa.Column('chemistry_json', sa.JSON(), nullable=False), created(),
                    sa.UniqueConstraint('project_id', 'structure_sha256', name='uq_registry_project_structure'))
    op.create_table('compound_batches', identity(), ref('compound_id', 'registered_compounds.id'),
                    text('name', 120), text('data_origin', 20), text('source_reference'), text('notes'), created(),
                    sa.UniqueConstraint('compound_id', 'name', name='uq_compound_batch_name'))
    op.create_table('material_samples', identity(), ref('batch_id', 'compound_batches.id'),
                    text('name', 120), text('location', 240), text('notes'), created(),
                    sa.UniqueConstraint('batch_id', 'name', name='uq_batch_sample_name'))
    op.create_table('assay_protocols', identity(), ref('project_id', 'projects.id'), text('name', 120),
                    text('target_id', 40), text('endpoint', 80), text('activity_type', 40), text('units', 40),
                    text('modality', 40), text('species', 120), text('constructs'), text('method'), text('conditions'),
                    text('source_reference'), created(),
                    sa.UniqueConstraint('project_id', 'name', name='uq_project_protocol_name'))
    op.create_table('assay_runs', identity(), ref('protocol_id', 'assay_protocols.id'), text('name', 120),
                    sa.Column('performed_on', sa.Date(), nullable=False), text('operator', 120), text('data_origin', 20),
                    text('source_reference'), text('notes'), created(),
                    sa.UniqueConstraint('protocol_id', 'name', name='uq_protocol_run_name'))
    op.create_table('assay_observations', identity(), ref('run_id', 'assay_runs.id'), ref('sample_id', 'material_samples.id'),
                    sa.Column('supersedes_id', sa.Integer(), sa.ForeignKey('assay_observations.id'), nullable=True),
                    text('source_record_id', 120), text('value_text', 80),
                    sa.Column('numeric_value', sa.Float(), nullable=False), text('relation', 4),
                    text('source_reference'), text('notes'), created(),
                    sa.UniqueConstraint('run_id', 'source_record_id', name='uq_run_source_record'),
                    sa.UniqueConstraint('supersedes_id', name='uq_observation_supersedes'))
    op.create_index('ix_assay_observations_sample_id', 'assay_observations', ['sample_id'])
    op.create_table('registration_imports', identity(), ref('project_id', 'projects.id'), text('status', 20),
                    text('input_sha256', 64), text('plan_sha256', 64), text('csv_content'),
                    sa.Column('settings_json', sa.JSON(), nullable=False), sa.Column('rows_json', sa.JSON(), nullable=False),
                    sa.Column('outcome_json', sa.JSON(), nullable=True), created())
    op.create_table('research_views', identity(), ref('project_id', 'projects.id'), text('name', 120),
                    sa.Column('criteria_json', sa.JSON(), nullable=False), text('criteria_sha256', 64), created(),
                    sa.UniqueConstraint('project_id', 'name', name='uq_project_research_view_name'))


def downgrade():
    for table in ['research_views', 'registration_imports', 'assay_observations', 'assay_runs',
                  'assay_protocols', 'material_samples', 'compound_batches', 'registered_compounds']:
        op.drop_table(table)
