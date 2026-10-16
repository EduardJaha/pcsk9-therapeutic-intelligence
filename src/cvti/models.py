from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cvti.db import Base

PREDICTION_LABEL = "Research hypothesis only; not a validated drug"


def utcnow():
    return datetime.now(timezone.utc)


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("source", "source_record_id"),
        Index("ix_measurements_source_target_type", "source", "target_id", "activity_type"),
        Index("ix_measurements_assay_id", "assay_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    source_record_id: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(String(40), default="CHEMBL2929")
    molecule_id: Mapped[str | None] = mapped_column(String(80))
    assay_id: Mapped[str | None] = mapped_column(String(80))
    raw_smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str] = mapped_column(Text)
    scaffold: Mapped[str] = mapped_column(Text)
    activity_type: Mapped[str] = mapped_column(String(20))
    pchembl_value: Mapped[float] = mapped_column(Float)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TargetEvidence(Base):
    __tablename__ = "target_evidence"
    __table_args__ = (
        UniqueConstraint("target_id", "disease_id"),
        Index("ix_target_evidence_target_score", "target_id", "association_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[str] = mapped_column(String(40))
    target_symbol: Mapped[str] = mapped_column(String(40))
    disease_id: Mapped[str] = mapped_column(String(80))
    disease_name: Mapped[str] = mapped_column(Text)
    association_score: Mapped[float] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (Index("ix_dataset_versions_source_created", "source", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str] = mapped_column(String(40))
    endpoint_group: Mapped[str | None] = mapped_column(String(80))
    snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    review_sha256: Mapped[str | None] = mapped_column(String(64))
    policy_sha256: Mapped[str] = mapped_column(String(64))
    records_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    review_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    policy_json: Mapped[dict] = mapped_column(JSON)
    records_json: Mapped[list] = mapped_column(JSON)
    stats_json: Mapped[dict] = mapped_column(JSON)


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (Index("ix_experiments_source_created", "data_source", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), default=1, server_default="1")
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    target_id: Mapped[str] = mapped_column(String(40))
    data_source: Mapped[str] = mapped_column(String(40))
    model_kind: Mapped[str] = mapped_column(String(60))
    activity_type: Mapped[str] = mapped_column(String(20))
    threshold_pchembl: Mapped[float] = mapped_column(Float)
    n_molecules: Mapped[int] = mapped_column(Integer)
    n_scaffolds: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(Text)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    protocol_id: Mapped[int | None] = mapped_column(ForeignKey("evaluation_protocols.id"), nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_experiment_id", "experiment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), default=1, server_default="1")
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    input_smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(120), default=PREDICTION_LABEL)


class EvaluationProtocol(Base):
    __tablename__ = 'evaluation_protocols'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey('dataset_versions.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    manifest_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    protocol_json: Mapped[dict] = mapped_column(JSON)


class ExternalEvaluation(Base):
    __tablename__ = 'external_evaluations'
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey('experiments.id'))
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey('dataset_versions.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    results_json: Mapped[dict] = mapped_column(JSON)


class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Collection(Base):
    __tablename__ = 'collections'
    __table_args__ = (UniqueConstraint('project_id', 'name', name='uq_collection_project_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'))
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CollectionMolecule(Base):
    __tablename__ = 'collection_molecules'
    __table_args__ = (UniqueConstraint('collection_id', 'canonical_smiles', name='uq_collection_structure'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey('collections.id'))
    input_smiles: Mapped[str] = mapped_column(Text)
    canonical_smiles: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default='')


class BatchJob(Base):
    __tablename__ = 'batch_jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id'))
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey('experiments.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    save_predictions: Mapped[bool] = mapped_column(default=False)
    input_rows: Mapped[list] = mapped_column(JSON)
    result_rows: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
