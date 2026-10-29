"""Presentation helpers for the Streamlit research workbench."""

from html import escape

import altair as alt
import streamlit as st

from cvti.dashboard_theme import GRAPHITE_STYLE


COLORS = ["#159c90", "#668ce5", "#c7923d", "#b77cbf", "#779e55", "#dc7585"]


def apply_style():
    st.markdown(GRAPHITE_STYLE, unsafe_allow_html=True)


def pill(text: str, tone: str = "teal") -> str:
    return f'<span class="pill {tone}">{escape(text)}</span>'


def hero(title: str, description: str, badges: list[str]):
    st.markdown(f'<div class="hero"><div class="eyebrow">PCSK9 · CARDIOVASCULAR RESEARCH</div>'
                f'<h1>{escape(title)}</h1><p>{escape(description)}</p>'
                f'{"".join(pill(badge) for badge in badges)}</div>', unsafe_allow_html=True)


def stat(label, value, detail, color="var(--lab-accent)"):
    st.markdown(f'<div class="stat-card"><div class="stat-label">{escape(str(label))}</div>'
                f'<div class="stat-value" style="color:{color}">{escape(str(value))}</div>'
                f'<div class="stat-detail">{escape(str(detail))}</div></div>', unsafe_allow_html=True)


def molecule_card(profile: dict, index: int = 1, badge: str | None = None):
    properties = profile["properties"]
    prediction = profile.get("prediction")
    if prediction:
        badge = f"{'Demo' if prediction['source'] == 'synthetic_fixture' else 'Model'} score {prediction['probability_exploratory_activity']:.3f}"
    smiles = escape(profile["canonical_smiles"], quote=True)
    st.markdown(f'<article class="molecule-card"><div class="molecule-top"><strong>Molecule {index:02}</strong>'
                f'{pill(badge or profile["formula"])}</div><div class="molecule-image">{profile["svg"]}</div>'
                f'<div class="molecule-smiles" title="{smiles}">{smiles}</div>'
                f'<div class="molecule-properties"><div><span>MW · g/mol</span><b>{properties["molecular_weight"]:.1f}</b></div>'
                f'<div><span>LOGP · calc.</span><b>{properties["logp"]:.2f}</b></div>'
                f'<div><span>TPSA · Å²</span><b>{properties["tpsa"]:.1f}</b></div></div></article>', unsafe_allow_html=True)


def validation_chart(evaluation: dict):
    labels = {"balanced_accuracy": "Balanced accuracy", "roc_auc": "ROC AUC", "average_precision": "Average precision"}
    rows = [{"Split": str(row["split"]), "Metric": label, "Score": row[key]}
            for row in evaluation["splits"] for key, label in labels.items()]
    chart = alt.Chart(alt.Data(values=rows)).mark_line(point=alt.OverlayMarkDef(size=65), strokeWidth=2).encode(
        x=alt.X("Split:O", title="Scaffold holdout", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 1.05]), title="Score"),
        color=alt.Color("Metric:N", scale=alt.Scale(range=COLORS[:3]), legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Metric:N", "Split:O", alt.Tooltip("Score:Q", format=".3f")]).properties(height=230)
    st.altair_chart(chart.configure_view(stroke=None), width="stretch")
