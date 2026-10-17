# First session: using PCSK9 Lab

Start with an empty workspace. You can explore molecular structures without importing a dataset or training a model. The optional demonstration below creates synthetic data only when you choose to load it.

## 1. Start the program on your Mac

In the first Terminal window:

```bash
cd "/Users/eduardjaha/Documents/ChatGPT/AI Drug Discovery"
source .venv/bin/activate
cvti db upgrade
uvicorn cvti.api:app --reload --host 127.0.0.1 --port 8000
```

Keep that window running. In a second Terminal window:

```bash
cd "/Users/eduardjaha/Documents/ChatGPT/AI Drug Discovery"
source .venv/bin/activate
streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Open [PCSK9 Lab](http://127.0.0.1:8501). If these services are already running, open the link directly. Stop each service with Control+C in its Terminal window when finished.

## 2. Understand the empty Overview

Choose **Overview** in the sidebar. An empty database has zero measurements, experiments, predictions and dataset versions. The model molecule count displays a dash until a model exists. Messages about missing models or assay reviews are expected.

Keep **Scoring model** set to **Structures only** for the next two steps. Molecule input forms start blank. This tutorial provides example SMILES to paste explicitly; profiling or comparing them does not import measurements or save predictions.

## 3. Build a molecule profile without a model

Choose **Molecule profile**. A SMILES is a text representation of a molecular structure. Paste this example into **SMILES**:

```text
CC(=O)Oc1ccccc1C(=O)O
```

Click **Build molecule profile**. Inspect the drawing, canonical SMILES, formula, scaffold and calculated properties:

- Molecular weight describes molecular mass.
- Calculated logP estimates partitioning between octanol and water.
- Polar surface area describes the molecule's polar surface.
- Hydrogen-bond donors, acceptors and rotatable bonds describe structural features.

These are calculated descriptors. They do not demonstrate PCSK9 binding, safety or therapeutic effectiveness. No prediction is saved by building a profile. **Preview model score** and **Save prediction** remain disabled until you have a model. This MVP requires a molecule with a ring scaffold.

## 4. Compare structures without a dataset

Choose **Compare molecules** and paste one SMILES per line:

```text
CC(=O)Oc1ccccc1C(=O)O
CC(=O)Nc1ccc(O)cc1
Cn1c(=O)c2c(ncn2C)n(C)c1=O
```

Click **Compare molecules**. You can compare two to six distinct supported molecules. Inspect the cards, change the **Property** selector and use **Download comparison CSV** to export the displayed results.

The chemical-space plot summarizes fingerprint differences among just these molecules. Its positions change when you change the comparison set. Position, color and property values are not drug rankings. Comparisons do not save prediction records.

You can stop here and keep your database empty.

## 5. Optional: load a synthetic demonstration

This step adds data to the database. Choose **Models & reports**, expand **Run a synthetic demonstration**, then click **Load offline demo fixture** once.

The fixture contains 24 invented measurements and two invented disease-evidence entries. No public API or paid service is needed. It demonstrates the application and is not a scientific PCSK9 dataset.

Click **Train baseline on synthetic fixture** once. Training saves an experiment, a linked dataset version and a model file. Repeating training creates another experiment.

Inspect the molecule and scaffold counts, active/inactive class counts and five scaffold holdouts. Molecule and scaffold overlap should both be zero within each train/test split. The splits overlap with one another, so their results are not five independent validations. Synthetic metrics have no established biological meaning.

## 6. Optional: preview and save a demonstration score

In the sidebar, change **Scoring model** from **Structures only** to your **Demo · experiment …** entry. If needed, click **Refresh workspace** first.

Return to **Molecule profile**, build a profile and click **Preview model score**. This computes a score without saving a prediction. The result names its experiment and dataset version and indicates whether the molecule or scaffold appeared in training.

Click **Save prediction** only when you want a database record. The **Saved predictions** count on Overview then increases. Each click saves a separate record.

You can also return to **Compare molecules** and click **Compare molecules** again to apply the selected model. Selecting a different model does not automatically replace an already displayed comparison. Comparisons remain previews even when scored.

All model scores are research hypotheses. Synthetic model scores are software demonstrations, not estimates of drug success.

## 7. Inspect and export what you created

- **Models & reports:** select an experiment under **Inspect experiment evaluation** and download its Markdown or JSON report. Each report includes the experiment's original dataset version, evaluation and limitations.
- **Datasets & evidence:** inspect stored dataset versions and checksums. The **Target evidence** tab labels invented fixture evidence as synthetic; this evidence is not used to train the molecular classifier.
- **Assay review:** remains empty after a synthetic demonstration. It shows preserved ChEMBL reviews only after a separate real-data review workflow.

## 8. Move to real data later

Follow the [assay curation policy](assay-curation.md) and the README's real-data workflow when you are ready. Save the raw snapshot, generate a review sheet, inspect original experimental sources with suitable assay expertise, and curate a version from the recorded decisions. The dashboard displays reviews; edits are made to a review CSV and imported as a new version.

Unreviewed ChEMBL data cannot train this baseline. A review may correctly retain zero usable measurements. Training also requires both label classes and enough distinct molecules and scaffolds; passing software checks alone does not establish scientific adequacy.

Your local records live in `data/cvti.db`; generated models live in `data/artifacts/`. Closing the browser or stopping the servers does not erase them.
