"""Store immutable dataset provenance and link experiments.

Revision ID: 6e4a2f9d1c08
Revises: 0b0d802d3cb4
"""

import hashlib
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "6e4a2f9d1c08"
down_revision = "0b0d802d3cb4"
branch_labels = None
depends_on = None


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(40), nullable=False),
        sa.Column("endpoint_group", sa.String(80)),
        sa.Column("snapshot_sha256", sa.String(64)),
        sa.Column("review_sha256", sa.String(64)),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("records_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("snapshot_blob", sa.LargeBinary()),
        sa.Column("review_blob", sa.LargeBinary()),
        sa.Column("policy_json", sa.JSON(), nullable=False),
        sa.Column("records_json", sa.JSON(), nullable=False),
        sa.Column("stats_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_dataset_versions_source_created", "dataset_versions", ["source", "created_at"])
    with op.batch_alter_table("experiments") as batch:
        batch.add_column(sa.Column("dataset_version_id", sa.Integer(), nullable=True))

    connection = op.get_bind()
    versions = sa.table("dataset_versions", *(
        sa.column("id", sa.Integer()), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("source", sa.String()), sa.column("status", sa.String()),
        sa.column("target_id", sa.String()), sa.column("endpoint_group", sa.String()),
        sa.column("snapshot_sha256", sa.String()), sa.column("review_sha256", sa.String()),
        sa.column("policy_sha256", sa.String()), sa.column("records_sha256", sa.String()),
        sa.column("manifest_sha256", sa.String()), sa.column("snapshot_blob", sa.LargeBinary()),
        sa.column("review_blob", sa.LargeBinary()), sa.column("policy_json", sa.JSON()),
        sa.column("records_json", sa.JSON()), sa.column("stats_json", sa.JSON()),
    ))
    experiments = sa.table("experiments", sa.column("id", sa.Integer()),
                           sa.column("dataset_version_id", sa.Integer()))
    old_rows = connection.execute(sa.text(
        "SELECT id, created_at, data_source, target_id, dataset_hash, n_molecules "
        "FROM experiments ORDER BY id"
    )).mappings()
    for row in old_rows:
        policy = {"kind": "legacy_unverified", "note": "Original snapshot and review were not recorded",
                  "legacy_dataset_hash": row["dataset_hash"]}
        stats = {"legacy_experiment_id": row["id"], "n_molecules": row["n_molecules"]}
        manifest = {"source": row["data_source"], "status": "legacy_unverified",
                    "target_id": row["target_id"], "endpoint_group": None,
                    "snapshot_sha256": None, "review_sha256": None,
                    "policy_sha256": _digest(policy), "records_sha256": _digest([]), "stats": stats}
        version_id = connection.execute(versions.insert().values(
            created_at=datetime.now(timezone.utc), source=row["data_source"],
            status="legacy_unverified", target_id=row["target_id"], endpoint_group=None,
            snapshot_sha256=None, review_sha256=None, policy_sha256=manifest["policy_sha256"],
            records_sha256=manifest["records_sha256"], manifest_sha256=_digest(manifest),
            snapshot_blob=None, review_blob=None, policy_json=policy, records_json=[], stats_json=stats,
        ).returning(versions.c.id)).scalar_one()
        connection.execute(experiments.update().where(experiments.c.id == row["id"]).values(
            dataset_version_id=version_id
        ))

    with op.batch_alter_table("experiments") as batch:
        batch.alter_column("dataset_version_id", nullable=False)
        batch.create_foreign_key("fk_experiments_dataset_version", "dataset_versions",
                                 ["dataset_version_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("experiments") as batch:
        batch.drop_constraint("fk_experiments_dataset_version", type_="foreignkey")
        batch.drop_column("dataset_version_id")
    op.drop_index("ix_dataset_versions_source_created", table_name="dataset_versions")
    op.drop_table("dataset_versions")
