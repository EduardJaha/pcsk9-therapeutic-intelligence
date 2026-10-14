"""Minimal local research dashboard. Start FastAPI before this app."""
import os

import httpx
import streamlit as st


API = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="PCSK9 Research MVP", layout="wide")
st.title("PCSK9 therapeutic intelligence")
st.warning("Research hypotheses only. Predictions are not validated drugs, efficacy claims, or clinical guidance.")


def call(method, path, **kwargs):
    try:
        with httpx.Client(timeout=30) as client:
            response = client.request(method, f"{API}{path}", **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        st.error(f"API unavailable or request failed: {exc}")
        return None


summary = call("GET", "/summary")
if summary:
    cols = st.columns(4)
    for col, key in zip(cols, ["measurements", "evidence_rows", "experiments", "predictions"]):
        col.metric(key.replace("_", " ").title(), summary[key])

st.subheader("Data and model")
st.caption("The fixture is entirely synthetic. Real records require the documented ChEMBL snapshot and assay review workflow before training.")
versions = call("GET", "/dataset-versions")
curated_versions = [v for v in versions or [] if v["source"] == "chembl_curated"]
if versions is not None and (not curated_versions or curated_versions[0]["status"] != "ready"):
    st.info("No current reviewed real-data training set is available. The split results below test the software with synthetic molecules only.")
left, right = st.columns(2)
if left.button("Load offline demo fixture"):
    result = call("POST", "/fixtures/load")
    if result:
        st.success(f"Loaded {result['inserted_measurements']} new synthetic measurements")
if right.button("Train baseline on synthetic fixture"):
    result = call("POST", "/experiments", json={"source": "synthetic_fixture"})
    if result:
        st.success(f"Experiment {result['id']} saved")
        st.json(result["metrics"])

runs = call("GET", "/experiments") or []
if runs:
    def reported_score(run, name):
        evaluation = run["metrics"].get("evaluation")
        return evaluation["summary"][name]["median"] if evaluation else run["metrics"].get(name)

    st.dataframe([{"ID": r["id"], "Dataset version": r["dataset_version_id"],
                   "Source": r["data_source"], "Molecules": r["n_molecules"],
                   "Scaffolds": r["n_scaffolds"],
                   "Evaluation": "5 scaffold splits" if r["metrics"].get("evaluation") else "older single split",
                   "Balanced accuracy": reported_score(r, "balanced_accuracy"),
                   "ROC AUC": reported_score(r, "roc_auc")} for r in runs], hide_index=True)
    st.caption("Five-split rows show medians; older rows show their single holdout score.")
    selected = st.selectbox("Inspect experiment evaluation", runs,
                            format_func=lambda r: f"Experiment {r['id']} — {r['data_source']}")
    metrics = selected["metrics"]
    evaluation = metrics.get("evaluation")
    if evaluation:
        st.write("Dataset class counts (inactive / active):", metrics["class_counts"])
        st.caption(evaluation["caveat"])
        st.dataframe([{"Split": row["split"],
                       "Train inactive": row["train_class_counts"]["inactive"],
                       "Train active": row["train_class_counts"]["active"],
                       "Test inactive": row["test_class_counts"]["inactive"],
                       "Test active": row["test_class_counts"]["active"],
                       "Balanced accuracy": row["balanced_accuracy"],
                       "ROC AUC": row["roc_auc"],
                       "Average precision": row["average_precision"],
                       "Train scaffolds": row["n_train_scaffolds"],
                       "Test scaffolds": row["n_test_scaffolds"]}
                      for row in evaluation["splits"]], hide_index=True)
        st.write("Median and range across splits:", evaluation["summary"])
        st.caption("The saved prediction model was refit on all molecules after evaluation.")
    else:
        st.info("This older experiment has only one scaffold holdout. Retrain to see repeated evaluation.")

st.subheader("Explore a molecule")
smiles = st.text_input("SMILES", value="CC1CCCCC1")
if st.button("Save exploratory prediction"):
    result = call("POST", "/predict", json={"smiles": smiles})
    if result:
        st.metric("Exploratory activity model score", f"{result['probability_exploratory_activity']:.3f}")
        st.info(result["label"])
        st.caption(f"Dataset version: {result['dataset_version_id']} ({result['dataset_version_status']})")
        if result["dataset_version_superseded"]:
            st.warning("This experiment used an older dataset version. Review its provenance before interpreting the score.")
        st.caption(f"Model source: {result['source']}; seen in training: {result['seen_in_training']}; scaffold seen in training: {result['scaffold_seen_in_training']}")

st.subheader("PCSK9 disease associations")
evidence = call("GET", "/evidence") or []
if evidence:
    st.dataframe(evidence, hide_index=True)
st.caption("Association scores summarize source evidence; they do not establish a treatment or compound mechanism. Synthetic IDs indicate demo data.")
