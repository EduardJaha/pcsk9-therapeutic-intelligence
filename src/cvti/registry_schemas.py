"""Validated inputs for the local registry; recorded assays never approve training."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Modality = Literal['small_molecule', 'macrocyclic_peptide', 'peptide', 'other']
Origin = Literal['research', 'synthetic']
Endpoint = Literal['pcsk9_ldlr_binding', 'pcsk9_expression', 'pcsk9_secretion', 'other_pcsk9']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    project_id: int = Field(default=1, gt=0)


class CompoundInput(Input):
    smiles: str = Field(min_length=1, max_length=1000)
    name: str = Field(default='', max_length=120)
    modality: Modality
    source_reference: Reference
    notes: str = Field(default='', max_length=4000)


class BatchInput(Input):
    compound_id: int = Field(gt=0)
    name: Name
    data_origin: Origin
    source_reference: Reference
    notes: str = Field(default='', max_length=4000)


class SampleInput(Input):
    batch_id: int = Field(gt=0)
    name: Name
    location: str = Field(default='', max_length=240)
    notes: str = Field(default='', max_length=4000)


class ProtocolInput(Input):
    name: Name
    endpoint: Endpoint
    activity_type: ShortText
    units: ShortText
    modality: Modality
    species: Name
    constructs: Reference
    method: Reference
    conditions: Reference
    source_reference: Reference


class RunInput(Input):
    protocol_id: int = Field(gt=0)
    name: Name
    performed_on: date
    operator: Name
    data_origin: Origin
    source_reference: Reference
    notes: str = Field(default='', max_length=4000)


class ObservationInput(Input):
    run_id: int = Field(gt=0)
    sample_id: int = Field(gt=0)
    supersedes_id: int | None = Field(default=None, gt=0)
    source_record_id: Name
    value_text: str = Field(min_length=1, max_length=80)
    relation: Literal['=', '<', '<=', '>', '>='] = '='
    units: ShortText
    source_reference: Reference
    notes: str = Field(default='', max_length=4000)


class ImportInput(Input):
    csv_content: str = Field(min_length=1, max_length=2_000_000)
    smiles_column: str = Field(min_length=1, max_length=200)
    name_column: str | None = Field(default=None, min_length=1, max_length=200)
    notes_column: str | None = Field(default=None, min_length=1, max_length=200)
    modality: Modality
    source_reference: Reference


class CommitInput(Input):
    plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CompoundFilter(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    schema_version: Literal[1] = 1
    name: str = Field(default='', max_length=120)
    modality: Modality | None = None
    query_smiles: str = Field(default='', max_length=1000)
    match_mode: Literal['none', 'exact', 'substructure', 'similarity'] = 'none'
    min_similarity: float = Field(default=0.5, ge=0, le=1)
    min_mw: float | None = Field(default=None, ge=0)
    max_mw: float | None = Field(default=None, ge=0)
    min_logp: float | None = None
    max_logp: float | None = None
    limit: int = Field(default=500, ge=1, le=1000)

    @model_validator(mode='after')
    def check_ranges(self):
        for lower, upper in [(self.min_mw, self.max_mw), (self.min_logp, self.max_logp)]:
            if lower is not None and upper is not None and lower > upper:
                raise ValueError('Minimum property value must not exceed maximum')
        if self.match_mode != 'none' and not self.query_smiles.strip():
            raise ValueError('A structure query is required for this match mode')
        if self.match_mode == 'none' and self.query_smiles.strip():
            raise ValueError('Choose a structure match mode for the SMILES query')
        return self


class WorkbenchInput(Input):
    criteria: CompoundFilter = Field(default_factory=CompoundFilter)


class ViewInput(WorkbenchInput):
    name: Name


class ScoreInput(Input):
    experiment_id: int = Field(gt=0)
    compound_ids: list[int] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_ids(self):
        if any(value <= 0 for value in self.compound_ids) or len(set(self.compound_ids)) != len(self.compound_ids):
            raise ValueError('Select distinct positive compound identifiers')
        return self
