"""Minimal local research dashboard. Start FastAPI before this app."""
import json
import os

import httpx
import streamlit as st

from cvti.reports import render_assay_review_csv, render_experiment_report


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
    st.info("The current ChEMBL review is not ready for real-data training. Synthetic demo experiments remain available.")
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

st.subheader("Assay review")
if curated_versions:
    review_version = st.selectbox("Assay review dataset version", curated_versions,
                                  format_func=lambda v: f"Version {v['id']} — {v['status']} ({v['created_at']})")
    st.caption(f"Snapshot retrieved: {review_version['stats'].get('snapshot_retrieved_at') or 'not recorded'}")
    review_payload = call("GET", f"/dataset-versions/{review_version['id']}/assays")
    if review_payload:
        assays = review_payload["assays"]
        st.caption("Decisions and sources come from this version's saved snapshot and review sheet. Included assays can still have activities removed by selection rules.")
        st.write({"Assays": len(assays), **{decision: sum(row["decision"] == decision for row in assays)
                                          for decision in ("include", "exclude", "pending")}})
        decision_filter = st.selectbox("Filter assay decisions", ["all", "include", "exclude", "pending"])
        visible = [row for row in assays if decision_filter == "all" or row["decision"] == decision_filter]
        if visible:
            st.dataframe([{"Assay": row["assay_id"], "Assay link": row["assay_url"],
                           "Source documents": ", ".join(doc["id"] for doc in row["source_documents"]),
                           "Decision": row["decision"], "Activities": row["activity_count"],
                           "Selected activities": row["selected_activity_count"],
                           "Exclusion reason": row["exclusion_reason"]} for row in visible],
                         column_config={"Assay link": st.column_config.LinkColumn("ChEMBL assay", display_text="Open assay")},
                         hide_index=True)
            detail = st.selectbox("Inspect assay", visible, format_func=lambda row: row["assay_id"])
            st.write("Assay description:", detail["description"] or "Not recorded")
            st.write("Recorded review note:", detail["review_note"] or "Not recorded")
            for source in detail["source_documents"]:
                st.markdown(f"[ChEMBL source document {source['id']}]({source['url']})")
            if not detail["source_documents"]:
                st.caption("No source document was recorded for this assay.")
            if detail["recorded_machine_issue"]:
                st.write("Recorded assay metadata exclusion:", detail["recorded_machine_issue"])
            if detail["activity_exclusions"]:
                st.write("Recorded activity exclusions:", detail["activity_exclusions"])
        else:
            st.info("No assays match this decision filter.")
        st.download_button("Download assay review CSV (all assays)", render_assay_review_csv(assays),
                           file_name=f"dataset-{review_version['id']}-assay-review.csv", mime="text/csv")
else:
    st.info("No ChEMBL review version is stored yet. Import a snapshot and review sheet to inspect assays here.")

st.subheader("Experiments and reports")
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
    report = call("GET", f"/experiments/{selected['id']}/report")
    if report:
        st.caption(f"The report uses experiment {selected['id']}'s dataset version {report['dataset_version']['id']}, including its recorded selection rules and assay decisions.")
        markdown_export, json_export = st.columns(2)
        markdown_export.download_button("Download experiment report (Markdown)", render_experiment_report(report),
                                        file_name=f"experiment-{selected['id']}.md", mime="text/markdown")
        json_export.download_button("Download experiment report (JSON)", json.dumps(report, indent=2),
                                    file_name=f"experiment-{selected['id']}.json", mime="application/json")

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
