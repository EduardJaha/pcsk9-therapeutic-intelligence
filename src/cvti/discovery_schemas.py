from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Structure(Strict):
    smiles: str = Field(min_length=1, max_length=1000)


class Screen(Strict):
    query: str = Field(min_length=1, max_length=1000)
    smiles: list[str] = Field(min_length=1, max_length=500)
    min_similarity: float = Field(default=0, ge=0, le=1)


class SAR(Strict):
    csv_content: str = Field(min_length=1, max_length=500000)
    similarity_threshold: float = Field(default=.5, ge=0, le=1)


class Analogs(Structure):
    transformations: list[Literal['Phenol O-methylation', 'Aryl methyl addition', 'Aryl fluorination']] = Field(min_length=1, max_length=3)


class Curve(Strict):
    concentrations: list[float] = Field(min_length=6, max_length=500)
    responses: list[float] = Field(min_length=6, max_length=500)
    units: Literal['M','mM','uM','µM','nM','pM']
    direction: Literal['increasing','decreasing']
    source_reference: str = Field(min_length=1, max_length=4000)
    data_origin: Literal['experimental','synthetic']
    assay_run_id: int | None = Field(default=None, gt=0)
    sample_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def linked_pair(self):
        if (self.assay_run_id is None) != (self.sample_id is None):
            raise ValueError('Provide both an assay run and a sample, or neither')
        if not self.source_reference.strip():
            raise ValueError('A source reference is required')
        return self


class Plate(Strict):
    positive: list[float] = Field(min_length=3, max_length=500)
    negative: list[float] = Field(min_length=3, max_length=500)


class Target(Strict):
    ensembl_id: str = Field(pattern=r'^ENSG[0-9]{11}$')
    pdb_id: str | None = Field(default=None, pattern=r'^[0-9][A-Za-z0-9]{3}$')


class ADMET(Strict):
    model_id: int = Field(gt=0)
    smiles: list[str] = Field(min_length=1, max_length=50)
    endpoints: list[str] = Field(min_length=1, max_length=9)


class Docking(Structure):
    receptor_pdbqt: str = Field(min_length=80, max_length=2_000_000)
    receptor_source: str = Field(min_length=1, max_length=4000)
    preparation_notes: str = Field(min_length=1, max_length=4000)
    target: str = Field(min_length=1, max_length=120)
    pocket_rationale: str = Field(min_length=1, max_length=4000)
    center: list[float] = Field(min_length=3, max_length=3)
    box_size: list[float] = Field(min_length=3, max_length=3)
    seed: int = Field(default=2026, ge=1, le=2147483647)
    exhaustiveness: int = Field(default=8, ge=1, le=16)
    n_poses: int = Field(default=9, ge=1, le=20)

    @field_validator('center')
    @classmethod
    def bounded_center(cls, values):
        if any(abs(v) > 10000 for v in values):
            raise ValueError('Docking center is outside supported bounds')
        return values

    @field_validator('box_size')
    @classmethod
    def bounded_box(cls, values):
        if any(not 5 <= v <= 40 for v in values):
            raise ValueError('Each box dimension must be 5–40 Å')
        return values

    @field_validator('receptor_source','preparation_notes','target','pocket_rationale')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Target, source, preparation and pocket rationale must be explicit')
        return value


ANALYSES = {'dossier': Structure, 'conformer': Structure, 'screen': Screen, 'sar': SAR,
            'analogs': Analogs, 'curve': Curve, 'plate': Plate, 'target': Target}
