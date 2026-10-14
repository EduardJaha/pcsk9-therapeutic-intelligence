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
st.caption("The fixture is entirely synthetic. For real public records, run `cvti ingest --source live` locally.")
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
    st.dataframe([{"ID": r["id"], "Source": r["data_source"], "Molecules": r["n_molecules"],
                   "Scaffolds": r["n_scaffolds"], "Balanced accuracy": r["metrics"]["balanced_accuracy"],
                   "ROC AUC": r["metrics"]["roc_auc"]} for r in runs], hide_index=True)

st.subheader("Explore a molecule")
smiles = st.text_input("SMILES", value="CC1CCCCC1")
if st.button("Save exploratory prediction"):
    result = call("POST", "/predict", json={"smiles": smiles})
    if result:
        st.metric("Exploratory activity model score", f"{result['probability_exploratory_activity']:.3f}")
        st.info(result["label"])
        st.caption(f"Model source: {result['source']}; seen in training: {result['seen_in_training']}; scaffold seen in training: {result['scaffold_seen_in_training']}")

st.subheader("PCSK9 disease associations")
evidence = call("GET", "/evidence") or []
if evidence:
    st.dataframe(evidence, hide_index=True)
st.caption("Association scores summarize source evidence; they do not establish a treatment or compound mechanism. Synthetic IDs indicate demo data.")
