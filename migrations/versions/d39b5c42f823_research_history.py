"""Preserve local history in projects and add persistent batch jobs."""
from alembic import op
import sqlalchemy as sa
revision = 'd39b5c42f823'
down_revision = 'c28a4b31e712'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('projects', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('name', sa.String(120), nullable=False), sa.Column('notes', sa.Text(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.execute("INSERT INTO projects (id,name,notes,created_at) VALUES (1,'Local project','Migrated projectless history',CURRENT_TIMESTAMP)")
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("SELECT setval(pg_get_serial_sequence('projects','id'),1)")
    for table in ['experiments', 'predictions']:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('project_id', sa.Integer(), nullable=False, server_default='1'))
            batch.create_foreign_key(f'fk_{table}_project', 'projects', ['project_id'], ['id'])
    op.create_table('collections', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
                    sa.Column('name', sa.String(120), nullable=False), sa.Column('notes', sa.Text(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint('project_id','name',name='uq_collection_project_name'))
    op.create_table('collection_molecules', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('collection_id', sa.Integer(), sa.ForeignKey('collections.id'), nullable=False),
                    sa.Column('input_smiles', sa.Text(), nullable=False), sa.Column('canonical_smiles', sa.Text(), nullable=False),
                    sa.Column('notes', sa.Text(), nullable=False),
                    sa.UniqueConstraint('collection_id','canonical_smiles',name='uq_collection_structure'))
    op.create_table('batch_jobs', sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
                    sa.Column('experiment_id', sa.Integer(), sa.ForeignKey('experiments.id'), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('status', sa.String(30), nullable=False), sa.Column('save_predictions', sa.Boolean(), nullable=False),
                    sa.Column('input_rows', sa.JSON(), nullable=False), sa.Column('result_rows', sa.JSON(), nullable=False),
                    sa.Column('error', sa.Text(), nullable=True))


def downgrade():
    for table in ['batch_jobs','collection_molecules','collections']:
        op.drop_table(table)
    for table in ['predictions','experiments']:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'fk_{table}_project', type_='foreignkey')
            batch.drop_column('project_id')
    op.drop_table('projects')
