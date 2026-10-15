"""Local PCSK9 research workbench. Start FastAPI before opening this app."""
import csv
import io
import json
import os
from html import escape

import altair as alt
import httpx
import streamlit as st

from cvti.dashboard_ui import COLORS, apply_style, hero, molecule_card, pill, stat, validation_chart
from cvti.reports import render_assay_review_csv, render_experiment_report


API = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
API_REFERENCE_URL = os.getenv("API_REFERENCE_URL", f"{API}/docs")
PAGES = ["Overview", "Molecule profile", "Compare molecules", "Assay review", "Models & reports", "Datasets & evidence"]
EXAMPLE_SMILES = "CC(=O)Oc1ccccc1C(=O)O\nCC(=O)Nc1ccc(O)cc1\nCn1c(=O)c2c(ncn2C)n(C)c1=O"
PROPERTIES = {
    "Molecular weight · g/mol": "molecular_weight", "Calculated logP": "logp",
    "Polar surface area · Å²": "tpsa", "H-bond donors": "h_bond_donors",
    "H-bond acceptors": "h_bond_acceptors", "Rotatable bonds": "rotatable_bonds",
}
st.set_page_config(page_title="PCSK9 Lab · Research workbench", page_icon="⚗", layout="wide")
apply_style()


def call(method, path, *, quiet=False, **kwargs):
    try:
        with httpx.Client(timeout=60) as client:
            response = client.request(method, f"{API}{path}", **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        if not quiet:
            try:
                detail = exc.response.json().get("detail", "Request failed")
            except ValueError:
                detail = f"The API returned an error ({exc.response.status_code}). Check the server and try again."
            st.error(detail if isinstance(detail, str) else "Check the input values and try again.")
    except httpx.HTTPError:
        if not quiet:
            st.error("The research API is unavailable. Start FastAPI and refresh this workspace.")
    return None


def source_name(source):
    return "Synthetic demo" if source == "synthetic_fixture" else "Reviewed ChEMBL" if source == "chembl_curated" else source


def chosen_model_note(model_id, runs):
    run = next((r for r in runs if r["id"] == model_id), None)
    if run:
        st.caption(f"Selected model: experiment {run['id']} · {source_name(run['data_source'])} · dataset {run['dataset_version_id']}")
        if run["data_source"] == "synthetic_fixture":
            st.info("Synthetic model selected. Its scores demonstrate the software and have no established biological meaning.")
    else:
        st.caption("Structures only. Select a scoring model in the sidebar to add exploratory PCSK9 scores.")


def review_rows(versions):
    curated = [v for v in versions if v["source"] == "chembl_curated"]
    if not curated:
        return None, []
    payload = call("GET", f"/dataset-versions/{curated[0]['id']}/assays")
    return curated[0], payload["assays"] if payload else []


def overview(summary, runs, versions):
    hero("Your cardiovascular discovery workspace",
         "Bring molecular structures, assay evidence and model evaluation into one traceable research workflow.",
         ["PCSK9–LDLR endpoint", "RDKit chemistry", "Scaffold evaluation", "Research use only"])
    version, assays = review_rows(versions)
    latest = runs[0] if runs else None
    retained = version["records"] if version and version["status"] == "ready" else 0
    columns = st.columns(4)
    with columns[0]:
        stat("Retained real activities", retained, "After review and selection rules", "#269f99")
    with columns[1]:
        stat("Assays reviewed", sum(a["decision"] != "pending" for a in assays), f"{len(assays)} assays in the current snapshot")
    with columns[2]:
        stat("Latest model molecules", latest["n_molecules"] if latest else "—",
             source_name(latest["data_source"]) if latest else "No model trained yet")
    with columns[3]:
        stat("Saved predictions", summary.get("predictions", 0), f"{summary.get('experiments', 0)} recorded experiments", "#4c80d9")
    if not retained:
        st.info("Real-data training is awaiting approved, comparable assay measurements. The synthetic demo is available for exploring the workflow.")
    left, right = st.columns([1.65, 1], gap="medium")
    with left, st.container(border=True, key="panel_overview_validation"):
        st.subheader("Scaffold validation")
        evaluation = latest["metrics"].get("evaluation") if latest else None
        if evaluation:
            validation_chart(evaluation)
            st.caption(f"Experiment {latest['id']} · {source_name(latest['data_source'])}. Each point is a separate holdout; overlapping holdouts are not independent evidence.")
        else:
            st.info("Train the synthetic baseline from Models & reports to see five scaffold holdouts.")
    with right, st.container(border=True, key="panel_overview_review"):
        st.subheader("Assay review readiness")
        if assays:
            counts = [{"Decision": decision.capitalize(), "Assays": sum(a["decision"] == decision for a in assays)}
                      for decision in ["include", "exclude", "pending"]]
            donut = alt.Chart(alt.Data(values=counts)).mark_arc(innerRadius=62, outerRadius=89).encode(
                theta="Assays:Q", color=alt.Color("Decision:N",
                    scale=alt.Scale(domain=["Include", "Exclude", "Pending"], range=["#269f99", "#b8b1e4", "#e2ba72"]),
                    legend=alt.Legend(orient="bottom", title=None)), tooltip=["Decision:N", "Assays:Q"])
            text = alt.Chart(alt.Data(values=[{"label": str(len(assays))}])).mark_text(
                fontSize=34, fontWeight=600, color="#514c74").encode(text="label:N")
            st.altair_chart((donut + text).properties(height=230).configure_view(stroke=None), width="stretch")
            st.caption(f"Dataset {version['id']} · {retained} retained activities. Review decisions are preserved with their source documents.")
        else:
            st.info("Import a ChEMBL snapshot and a review sheet to begin.")
    st.subheader("A look inside your molecule collection")
    st.caption("Structures from stored measurements. Calculated properties describe the molecule; they are not measured ADMET endpoints.")
    measurements = call("GET", "/measurements?limit=3") or []
    if measurements:
        for index, (column, row) in enumerate(zip(st.columns(len(measurements)), measurements), start=1):
            with column:
                profile = call("POST", "/molecules/profile", json={"smiles": row["canonical_smiles"]})
                if profile:
                    molecule_card(profile, index, badge=source_name(row["source"]))
    else:
        st.info("Load the offline fixture in Models & reports to populate the demo workspace.")


def comparison(model_id, runs):
    hero("Compare molecules, structure by structure",
         "Inspect up to six molecular structures, compare calculated properties and explore their relative chemical space.",
         ["2–6 molecules", "Calculated descriptors", "Morgan fingerprint PCA", "Explicit model selection"])
    editor, workspace = st.columns([0.85, 2.15], gap="medium")
    with editor, st.container(border=True, key="panel_compare_editor"):
        st.subheader("Compare molecules")
        with st.form("comparison_form"):
            text = st.text_area("One SMILES per line (2–6)", EXAMPLE_SMILES, height=210)
            submitted = st.form_submit_button("Compare molecules", type="primary", width="stretch")
        chosen_model_note(model_id, runs)
        st.caption("Example structures are for exploring the interface. A model score is not a desirability score or a validated drug ranking.")
        if submitted:
            st.session_state.pop("comparison_result", None)
            result = call("POST", "/molecules/compare",
                          json={"smiles": [line.strip() for line in text.splitlines() if line.strip()],
                                "experiment_id": model_id})
            if result:
                st.session_state["comparison_result"] = result
        if "comparison_result" not in st.session_state and not submitted:
            result = call("POST", "/molecules/compare",
                          json={"smiles": EXAMPLE_SMILES.splitlines(), "experiment_id": None})
            if result:
                st.session_state["comparison_result"] = result
    result = st.session_state.get("comparison_result")
    with workspace:
        if not result:
            st.info("Enter two to six ring-containing molecules and run a comparison.")
            return
        profiles = result["molecules"]
        run_id = result["experiment_id"]
        st.caption(f"Displayed comparison: experiment {run_id}. Predictions are previews and are not saved." if run_id else
                   "Structure preview · calculated properties only. Press Compare molecules to apply your selected model.")
        if run_id is not None and run_id != model_id:
            st.caption("The selected model has changed. Run the comparison to update these displayed results.")
        if any(p.get("prediction") and p["prediction"]["dataset_version_status"] == "legacy_unverified" for p in profiles):
            st.warning("This comparison uses a legacy model with incomplete original provenance. Inspect its experiment report before interpreting the scores.")
        elif any(p.get("prediction") and p["prediction"]["dataset_version_superseded"] for p in profiles):
            st.caption("A newer dataset version exists. These scores retain the selected experiment's original dataset.")
        for start in range(0, len(profiles), 3):
            for index, (column, profile) in enumerate(zip(st.columns(min(3, len(profiles) - start)), profiles[start:start + 3]), start=start + 1):
                with column:
                    molecule_card(profile, index)
        export_rows = []
        for index, profile in enumerate(profiles, start=1):
            prediction = profile["prediction"]
            export_rows.append({"molecule": index, "canonical_smiles": profile["canonical_smiles"],
                                "formula": profile["formula"], **profile["properties"],
                                "experiment_id": run_id, "dataset_version_id": prediction["dataset_version_id"] if prediction else None,
                                "model_source": prediction["source"] if prediction else None,
                                "exploratory_score": prediction["probability_exploratory_activity"] if prediction else None,
                                "research_notice": "Research hypothesis only; not validated ADMET or drug efficacy"})
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(export_rows[0]))
        writer.writeheader()
        writer.writerows(export_rows)
        st.download_button("Download comparison CSV", buffer.getvalue(), file_name="molecule-comparison.csv", mime="text/csv")
        properties_panel, space_panel = st.columns(2, gap="medium")
        with properties_panel, st.container(border=True, key="panel_compare_properties"):
            st.subheader("Molecular property comparison")
            property_label = st.selectbox("Property", list(PROPERTIES))
            rows = [{"Molecule": f"Molecule {index + 1}", "Value": profile["properties"][PROPERTIES[property_label]]}
                    for index, profile in enumerate(profiles)]
            chart = alt.Chart(alt.Data(values=rows)).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=34).encode(
                x=alt.X("Molecule:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Value:Q", title=property_label),
                color=alt.Color("Molecule:N", scale=alt.Scale(range=COLORS), legend=None),
                tooltip=["Molecule:N", "Value:Q"]).properties(height=230)
            st.altair_chart(chart.configure_view(stroke=None), width="stretch")
            st.caption("RDKit-calculated properties. Bars do not represent therapeutic quality.")
        with space_panel, st.container(border=True, key="panel_compare_space"):
            st.subheader("Chemical space")
            points = result["chemical_space"]["points"]
            chart = alt.Chart(alt.Data(values=points)).mark_circle(size=160, opacity=0.85, stroke="white", strokeWidth=2).encode(
                x=alt.X("pc1:Q", title="PC1"), y=alt.Y("pc2:Q", title="PC2"),
                color=alt.Color("molecule:N", scale=alt.Scale(range=COLORS), legend=None),
                tooltip=[alt.Tooltip("molecule:N", title="Molecule"), alt.Tooltip("canonical_smiles:N", title="SMILES")]).properties(height=230)
            st.altair_chart(chart.configure_view(stroke=None), width="stretch")
            st.caption("Morgan-fingerprint PCA of these molecules only. Distances are a structural visualization, not a validated applicability domain.")


def profile_page(model_id, runs):
    hero("Explore a molecular profile",
         "Start with a structure, inspect its calculated properties and choose a recorded model for an exploratory PCSK9 score.",
         ["2D structure", "Canonical SMILES", "Calculated properties", "Research hypothesis"])
    entry, details = st.columns([0.85, 2.15], gap="medium")
    with entry, st.container(border=True, key="panel_profile_editor"):
        st.subheader("Molecule input")
        with st.form("profile_form"):
            smiles = st.text_input("SMILES", "CC(=O)Oc1ccccc1C(=O)O", max_chars=1000)
            submitted = st.form_submit_button("Build molecule profile", type="primary", width="stretch")
        if submitted:
            st.session_state.pop("molecule_profile", None)
            st.session_state.pop("profile_prediction", None)
        if submitted or "molecule_profile" not in st.session_state:
            profile = call("POST", "/molecules/profile", json={"smiles": smiles})
            if profile:
                st.session_state["molecule_profile"] = profile
                st.session_state.pop("profile_prediction", None)
        chosen_model_note(model_id, runs)
        profile = st.session_state.get("molecule_profile")
        if profile:
            if st.button("Preview model score", disabled=model_id is None, width="stretch"):
                prediction = call("POST", "/predict", json={"smiles": profile["canonical_smiles"],
                                                           "experiment_id": model_id, "save": False})
                if prediction:
                    st.session_state["profile_prediction"] = prediction
            if st.button("Save prediction", disabled=model_id is None, width="stretch"):
                prediction = call("POST", "/predict", json={"smiles": profile["canonical_smiles"],
                                                           "experiment_id": model_id, "save": True})
                if prediction:
                    st.session_state["profile_prediction"] = prediction
                    st.success(f"Prediction {prediction['prediction_id']} saved with experiment {prediction['experiment_id']}.")
        st.caption("The current pipeline supports molecules with a ring scaffold. Scores use the explicitly selected model.")
    with details:
        profile = st.session_state.get("molecule_profile")
        if not profile:
            st.info("Enter a supported SMILES structure to build its profile.")
            return
        structure, properties = st.columns([1, 1.2])
        with structure:
            molecule_card(profile, badge="Calculated structure")
        with properties, st.container(border=True, key="panel_profile_properties"):
            st.subheader("Calculated molecular properties")
            st.dataframe([{"Property": label, "Value": profile["properties"][key]} for label, key in PROPERTIES.items()],
                         hide_index=True, width="stretch")
            st.caption(profile["notice"])
        with st.container(border=True, key="panel_profile_score"):
            st.subheader("Exploratory PCSK9 score")
            prediction = st.session_state.get("profile_prediction")
            if prediction:
                st.markdown(f'<div class="score">{prediction["probability_exploratory_activity"]:.3f}</div>', unsafe_allow_html=True)
                st.caption(f"Experiment {prediction['experiment_id']} · dataset {prediction['dataset_version_id']} · {source_name(prediction['source'])}")
                st.info(prediction["label"])
                if prediction["experiment_id"] != model_id:
                    st.caption("This score belongs to the displayed experiment. Preview again to apply the newly selected model.")
                if prediction["dataset_version_superseded"] or prediction["dataset_version_status"] == "legacy_unverified":
                    st.warning("This model uses an older or unverified dataset version. Inspect its experiment report before interpreting the score.")
                st.write({"Exact molecule seen in training": prediction["seen_in_training"],
                          "Scaffold seen in training": prediction["scaffold_seen_in_training"]})
            else:
                st.caption("Choose a model and preview its score. Opening this profile does not save a prediction.")
            st.caption("Available model endpoint: exploratory IC50 activity class. ADMET, calibrated uncertainty and docking models have not been established.")
        with st.expander("Structure identifiers"):
            st.write("Formula:", profile["formula"])
            st.code(profile["canonical_smiles"], language=None)
            st.write("Scaffold")
            st.code(profile["scaffold"], language=None)


def assay_page(versions):
    hero("Review the evidence behind each assay",
         "Inspect source documents, inclusion decisions and exclusion reasons exactly as they were preserved in a dataset version.",
         ["Source-linked evidence", "Recorded decisions", "Immutable history", "CSV export"])
    curated = [v for v in versions if v["source"] == "chembl_curated"]
    if not curated:
        st.info("No ChEMBL review version is stored yet. Import a snapshot and review sheet to begin.")
        return
    version = st.selectbox("Assay review dataset version", curated,
                           format_func=lambda v: f"Dataset {v['id']} · {v['status']} · {v['created_at'][:10]}")
    payload = call("GET", f"/dataset-versions/{version['id']}/assays")
    if not payload:
        return
    assays = payload["assays"]
    for column, decision, color in zip(st.columns(3), ["include", "exclude", "pending"], ["#269f99", "#ad7188", "#d4a246"]):
        with column:
            stat(decision.capitalize(), sum(a["decision"] == decision for a in assays), "Recorded assay decisions", color)
    st.caption(f"Snapshot retrieved: {version['stats'].get('snapshot_retrieved_at') or 'not recorded'}. Inclusion does not guarantee that activities survived every selection rule.")
    table, inspector = st.columns([1.8, 1], gap="medium")
    with table, st.container(border=True, key="panel_assay_table"):
        st.subheader("Assay register")
        filter_column, search_column = st.columns([1, 1.5])
        with filter_column:
            decision = st.selectbox("Filter assay decisions", ["all", "include", "exclude", "pending"])
        with search_column:
            search = st.text_input("Search assays", placeholder="Assay ID, description or review note").strip().casefold()
        visible = [a for a in assays if (decision == "all" or a["decision"] == decision)
                   and (not search or search in " ".join([a["assay_id"], a["description"], a["review_note"]]).casefold())]
        st.dataframe([{"Assay": a["assay_id"], "Decision": a["decision"], "Activities": a["activity_count"],
                       "Retained": a["selected_activity_count"], "Exclusion reason": a["exclusion_reason"],
                       "Source documents": ", ".join(doc["id"] for doc in a["source_documents"]),
                       "Assay link": a["assay_url"]} for a in visible],
                     column_config={"Assay link": st.column_config.LinkColumn("ChEMBL assay", display_text="Open assay")},
                     hide_index=True, width="stretch")
        if not visible:
            st.info("No assays match these filters.")
        st.download_button("Download assay review CSV (all assays)", render_assay_review_csv(assays),
                           file_name=f"dataset-{version['id']}-assay-review.csv", mime="text/csv")
    with inspector, st.container(border=True, key="panel_assay_detail"):
        st.subheader("Evidence inspector")
        if not visible:
            st.caption("Select a matching assay to inspect its evidence.")
            return
        assay = st.selectbox("Inspect assay", visible, format_func=lambda a: a["assay_id"])
        st.markdown(pill(assay["decision"].capitalize(), "green" if assay["decision"] == "include" else "rose"), unsafe_allow_html=True)
        st.write("Assay description")
        st.write(assay["description"] or "Not recorded")
        st.write("Recorded review note")
        st.write(assay["review_note"] or "Not recorded")
        for document in assay["source_documents"]:
            st.link_button(f"Source document · {document['id']}", document["url"], width="stretch")
        if not assay["source_documents"]:
            st.caption("No source document was recorded.")
        if assay["recorded_machine_issue"]:
            st.caption(f"Recorded metadata exclusion: {assay['recorded_machine_issue']}")
        if assay["activity_exclusions"]:
            st.write("Recorded activity exclusions", assay["activity_exclusions"])


def models_page(runs, versions):
    hero("Models, evaluation & experiment reports",
         "Compare scaffold holdouts, inspect class balance and export the complete record behind a saved experiment.",
         ["Five scaffold holdouts", "Class counts", "Dataset provenance", "Portable reports"])
    with st.expander("Run a synthetic demonstration"):
        st.caption("The fixture and its labels are invented for software testing. Real-data training remains governed by assay review.")
        load, train = st.columns(2)
        if load.button("Load offline demo fixture", width="stretch"):
            loaded = call("POST", "/fixtures/load")
            if loaded:
                st.session_state["workspace_notice"] = f"Loaded {loaded['inserted_measurements']} new synthetic measurements."
                st.rerun()
        if train.button("Train baseline on synthetic fixture", type="primary", width="stretch"):
            with st.spinner("Evaluating scaffold splits and saving the model…"):
                trained = call("POST", "/experiments", json={"source": "synthetic_fixture"})
            if trained:
                st.session_state["workspace_notice"] = f"Experiment {trained['id']} saved and ready to inspect."
                st.rerun()
    if not runs:
        st.info("Load the fixture and train a demonstration model to begin.")
        return
    run = st.selectbox("Inspect experiment evaluation", runs,
                       format_func=lambda r: f"Experiment {r['id']} · {source_name(r['data_source'])} · dataset {r['dataset_version_id']}")
    evaluation = run["metrics"].get("evaluation")
    counts = run["metrics"].get("class_counts", {})
    for column, label, value, detail in zip(st.columns(4),
            ["Molecules", "Scaffolds", "Active / inactive", "Evaluation splits"],
            [run["n_molecules"], run["n_scaffolds"],
             f"{counts.get('active', '—')} / {counts.get('inactive', '—')}",
             len(evaluation["splits"]) if evaluation else 1],
            [source_name(run["data_source"]), "Bemis–Murcko groups", "Illustrative IC50 label", "Distinct scaffold partitions"]):
        with column:
            stat(label, value, detail)
    if run["data_source"] == "synthetic_fixture":
        st.info("Synthetic experiment. These metrics assess the demonstration workflow and carry no evidence of biological performance.")
    if evaluation:
        charts, distribution = st.columns([1.4, 1], gap="medium")
        with charts, st.container(border=True, key="panel_models_validation"):
            st.subheader("Performance across scaffold splits")
            validation_chart(evaluation)
            st.caption(evaluation["caveat"])
        with distribution, st.container(border=True, key="panel_models_distribution"):
            st.subheader("Test-set class balance")
            rows = [{"Split": str(row["split"]), "Class": name.capitalize(), "Molecules": count}
                    for row in evaluation["splits"] for name, count in row["test_class_counts"].items()]
            chart = alt.Chart(alt.Data(values=rows)).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=28).encode(
                x=alt.X("Split:O", title="Scaffold holdout", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Molecules:Q", axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("Class:N", scale=alt.Scale(range=COLORS[:2]), legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["Split:O", "Class:N", "Molecules:Q"]).properties(height=230)
            st.altair_chart(chart.configure_view(stroke=None), width="stretch")
            st.caption("Both classes are required in every training and test partition.")
        with st.container(border=True, key="panel_models_results"):
            st.subheader("Split-by-split results")
            st.dataframe([{"Split": row["split"], "Train inactive": row["train_class_counts"]["inactive"],
                           "Train active": row["train_class_counts"]["active"], "Test inactive": row["test_class_counts"]["inactive"],
                           "Test active": row["test_class_counts"]["active"], "Balanced accuracy": row["balanced_accuracy"],
                           "ROC AUC": row["roc_auc"], "Average precision": row["average_precision"],
                           "Molecule overlap": row["molecule_overlap"], "Scaffold overlap": row["scaffold_overlap"]}
                          for row in evaluation["splits"]], hide_index=True, width="stretch")
            st.caption("The saved prediction model was refit on all version molecules after these evaluation fits.")
    else:
        st.info("This older experiment has a single holdout. Retrain to obtain repeated scaffold evaluation.")
    report = call("GET", f"/experiments/{run['id']}/report")
    if report:
        with st.container(border=True, key="panel_models_report"):
            st.subheader("Export experiment report")
            st.caption(f"Dataset version {report['dataset_version']['id']} · {report['dataset_version']['status']}. Reports retain this experiment's original review, source checksums and selection rules.")
            markdown, json_column = st.columns(2)
            markdown.download_button("Download experiment report (Markdown)", render_experiment_report(report),
                                     file_name=f"experiment-{run['id']}.md", mime="text/markdown", width="stretch")
            json_column.download_button("Download experiment report (JSON)", json.dumps(report, indent=2),
                                        file_name=f"experiment-{run['id']}.json", mime="application/json", width="stretch")
    with st.expander("Experiment register and complete metrics"):
        st.dataframe([{"Experiment": r["id"], "Source": source_name(r["data_source"]),
                       "Dataset": r["dataset_version_id"], "Molecules": r["n_molecules"], "Created": r["created_at"]}
                      for r in runs], hide_index=True, width="stretch")
        st.json(run["metrics"])


def datasets_page(versions):
    hero("A traceable foundation for every experiment",
         "Inspect preserved dataset versions, their checksums and the contextual disease evidence stored in your workspace.",
         ["Versioned snapshots", "Review history", "Selection rules", "Source separation"])
    dataset_tab, evidence_tab = st.tabs(["Dataset versions", "Target evidence"])
    with dataset_tab:
        if not versions:
            st.info("No dataset versions are stored yet.")
        else:
            st.dataframe([{"Version": v["id"], "Source": source_name(v["source"]), "Status": v["status"],
                           "Retained records": v["records"], "Created": v["created_at"]} for v in versions],
                         hide_index=True, width="stretch")
            version = st.selectbox("Inspect dataset provenance", versions,
                                   format_func=lambda v: f"Dataset {v['id']} · {source_name(v['source'])} · {v['status']}")
            detail = call("GET", f"/dataset-versions/{version['id']}")
            if detail:
                with st.container(border=True, key="panel_dataset_provenance"):
                    st.subheader("Preserved provenance")
                    st.write("Endpoint:", detail["endpoint_group"] or "Synthetic or legacy dataset")
                    for name in ["snapshot", "review", "policy", "records", "manifest"]:
                        st.caption(f"{name.capitalize()} SHA-256")
                        st.code(detail.get(f"{name}_sha256") or "Not recorded", language=None)
                    with st.expander("Stored selection rules and curation counts"):
                        st.json({"policy": detail["policy"], "stats": detail["stats"]})
        with st.expander("Import and review workflow"):
            st.caption("Save a snapshot, prepare the review sheet, inspect original experimental sources, then curate a new version.")
            st.code("cvti chembl snapshot --output data/pcsk9-snapshot.json\n"
                    "cvti chembl review-sheet --snapshot data/pcsk9-snapshot.json --output data/review.csv\n"
                    "cvti chembl curate --snapshot data/pcsk9-snapshot.json --review data/review.csv", language="bash")
    with evidence_tab:
        st.subheader("PCSK9 disease association evidence")
        evidence = call("GET", "/evidence") or []
        st.dataframe([{**row, "Evidence source": "Synthetic demo" if row["disease_id"].startswith("SYNTHETIC") else "Open Targets"}
                      for row in evidence], hide_index=True, width="stretch")
        st.caption("Association evidence provides context and is not a feature used by the molecular classifier. Synthetic entries have no biological interpretation.")


summary = call("GET", "/summary", quiet=True)
connected = summary is not None
runs = (call("GET", "/experiments") or []) if connected else []
versions = (call("GET", "/dataset-versions") or []) if connected else []
with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-mark">P9</div><div><div class="brand-name">PCSK9 Lab</div>'
                '<div class="brand-caption">RESEARCH WORKBENCH</div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-caption">WORKSPACE</div>', unsafe_allow_html=True)
    initial_page = st.query_params.get("view", "Overview")
    st.session_state.setdefault("workspace_nav", initial_page if initial_page in PAGES else "Overview")
    def update_view():
        st.query_params["view"] = st.session_state["workspace_nav"]
    page = st.radio("Workspace", PAGES, label_visibility="collapsed", key="workspace_nav", on_change=update_view)
    st.divider()
    st.markdown('<div class="nav-caption">SCORING MODEL</div>', unsafe_allow_html=True)
    options = [None] + [run["id"] for run in runs]
    st.session_state.setdefault("scoring_model", runs[0]["id"] if runs else None)
    if st.session_state["scoring_model"] not in options:
        st.session_state["scoring_model"] = None
    def model_label(value):
        if value is None:
            return "Structures only"
        run = next(r for r in runs if r["id"] == value)
        return f"{'Demo' if run['data_source'] == 'synthetic_fixture' else 'ChEMBL'} · experiment {value}"
    model_id = st.selectbox("Scoring model", options, key="scoring_model", format_func=model_label, label_visibility="collapsed")
    st.caption("Used explicitly for profile scores and molecule comparisons.")
    st.markdown('<div class="sidebar-note"><strong>Evidence before confidence</strong>'
                'All model outputs are research hypotheses. Synthetic scores demonstrate software behavior only.</div>', unsafe_allow_html=True)
    st.link_button("Open API reference", API_REFERENCE_URL, width="stretch")
    if st.button("Refresh workspace", width="stretch"):
        st.rerun()
st.markdown(f'<div class="topbar"><div class="breadcrumb">Research workspace /<strong>{escape(page)}</strong></div>'
            f'<div class="topbadges">{pill("API connected" if connected else "API offline", "green" if connected else "rose")}'
            f'{pill("PCSK9 · 1 model endpoint")}{pill("Local research", "purple")}</div></div>', unsafe_allow_html=True)
if notice := st.session_state.pop("workspace_notice", None):
    st.toast(notice)
if not connected:
    st.error("The research API is unavailable. Start it with: uvicorn cvti.api:app --host 127.0.0.1 --port 8000")
    st.stop()
if page == "Overview":
    overview(summary or {}, runs, versions)
elif page == "Molecule profile":
    profile_page(model_id, runs)
elif page == "Compare molecules":
    comparison(model_id, runs)
elif page == "Assay review":
    assay_page(versions)
elif page == "Models & reports":
    models_page(runs, versions)
else:
    datasets_page(versions)
st.markdown('<div class="app-footer"><span>PCSK9 Lab · Research hypotheses only. Not validated drugs or clinical guidance.</span>'
            '<span>Python · RDKit · scikit-learn</span></div>', unsafe_allow_html=True)
