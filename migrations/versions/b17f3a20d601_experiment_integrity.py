"""Add training provenance and artifact checksums without inventing legacy history."""
from alembic import op
import sqlalchemy as sa
revision = 'b17f3a20d601'
down_revision = '6e4a2f9d1c08'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('experiments') as batch:
        batch.add_column(sa.Column('provenance_json', sa.JSON(), nullable=True))
        batch.add_column(sa.Column('artifact_sha256', sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table('experiments') as batch:
        batch.drop_column('artifact_sha256')
        batch.drop_column('provenance_json')
