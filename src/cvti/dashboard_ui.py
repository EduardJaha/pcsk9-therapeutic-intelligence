"""Presentation helpers for the Streamlit research workbench."""

from html import escape

import altair as alt
import streamlit as st


COLORS = ["#6854d8", "#269f99", "#dc9c39", "#4c80d9", "#bb70a6", "#8ca741"]


def apply_style():
    st.markdown("""<style>
    :root { --ink:#20273c; --muted:#788096; --purple:#6854d8; --line:#e6e9f2; }
    .stApp { background:#f3f5fa; color:var(--ink); }
    [data-testid="stHeader"] { background:rgba(243,245,250,.94); }
    .block-container { padding:3rem 1.5rem 2rem; max-width:1650px; }
    [data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); min-width:228px; max-width:228px; }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top:1rem; }
    [data-testid="stSidebarHeader"] { height:20px; margin-bottom:10px; }
    [data-testid="stSidebar"] .block-container { padding:1.2rem; }
    [data-testid="stSidebar"] hr { margin:1.1rem 0; border-color:var(--line); }
    [data-testid="stRadio"] label { padding:7px 10px; border-radius:9px; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:#eeebfc; color:#5141b0; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size:14px; font-weight:550; }
    .brand { display:flex; align-items:center; gap:10px; margin:0 0 22px; }
    .brand-mark { background:linear-gradient(140deg,#7464e7,#435cad); color:white; border-radius:12px; padding:9px 10px; font-size:21px; font-weight:800; letter-spacing:-1px; box-shadow:0 4px 10px #6653c929; }
    .brand-name { font-size:23px; line-height:1.1; font-weight:780; letter-spacing:-.8px; }
    .brand-caption { font-size:8px; letter-spacing:1.8px; color:#7e8498; margin-top:5px; font-weight:750; }
    .nav-caption { color:#9399ab; font-size:10px; letter-spacing:1.7px; font-weight:700; margin:15px 0 10px; }
    .sidebar-note { background:#f5f4fc; border:1px solid #e9e5fa; padding:13px; border-radius:12px; font-size:12px; color:#75728f; line-height:1.6; }
    .sidebar-note strong { color:#554a8e; display:block; margin-bottom:4px; }
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:0 0 20px; }
    .breadcrumb { font-size:12px; color:#9399aa; }
    .breadcrumb strong { color:#424a62; margin-left:9px; font-weight:600; }
    .topbadges { display:flex; gap:7px; flex-wrap:wrap; }
    .pill { display:inline-flex; align-items:center; gap:5px; background:#fff; border:1px solid #e4e7f0; border-radius:20px; padding:5px 10px; font-size:10px; font-weight:650; color:#626981; }
    .pill.purple { background:#f0edfd; border-color:#e5dffd; color:#6653bf; }
    .pill.green { background:#eff9f5; border-color:#dcefe6; color:#32816b; }
    .pill.amber { background:#fff8eb; border-color:#f2e4c3; color:#9c752f; }
    .pill.rose { background:#fff0f1; border-color:#f7dfe3; color:#b35d71; }
    .hero { border:1px solid #e5e5f3; background:linear-gradient(115deg,#ece9fb 0%,#eff1ff 52%,#eaf7f9 100%); padding:20px 24px; border-radius:17px; margin-bottom:17px; }
    .eyebrow { font-size:9px; letter-spacing:1.8px; color:#7c73aa; font-weight:750; margin-bottom:7px; }
    .hero h1 { margin:0 0 8px; padding:0 !important; font-size:29px; line-height:1.2; font-weight:760; letter-spacing:-.8px; color:#27273e; }
    .hero p { color:#767c92; font-size:12px; line-height:1.7; margin:0 0 14px; max-width:880px; }
    .hero .pill { background:#ffffffab; margin:0 5px 0 0; }
    .stat-card { background:#fff; border:1px solid var(--line); border-radius:13px; padding:17px 19px; min-height:112px; box-shadow:0 3px 12px #222b4f04; margin-bottom:12px; }
    .stat-label { font-size:10px; text-transform:uppercase; letter-spacing:1px; color:#8a90a3; font-weight:650; }
    .stat-value { font-size:31px; font-weight:720; letter-spacing:-1px; margin:5px 0 3px; line-height:1.2; }
    .stat-detail { font-size:10px; color:#9aa0b1; }
    [data-testid="stVerticalBlockBorderWrapper"] > div, [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][style*="border"] { border-color:var(--line) !important; border-radius:14px !important; background:white; }
    [class*="st-key-panel_"] { background:white; border-color:var(--line) !important; border-radius:14px !important; }
    [data-testid="stForm"] { border:0; padding:0; }
    [data-testid="stTextArea"] textarea { background:#f7f8fc; border:1px solid #eaecf4; }
    [data-testid="stExpander"] { background:white; border-color:var(--line); border-radius:12px; }
    h2 { font-size:20px !important; letter-spacing:-.45px; }
    h3 { font-size:15px !important; letter-spacing:-.25px; }
    [data-testid="stCaptionContainer"] p { font-size:11px; line-height:1.6; color:#8a90a3; }
    .stButton button, .stDownloadButton button, .stLinkButton a { border-radius:9px; font-size:12px; font-weight:600; }
    .stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] { background:linear-gradient(100deg,#6351d2,#8071ed); border:0; box-shadow:0 4px 10px #6b55d829; }
    [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input { font-size:12px; border-radius:9px; }
    .molecule-card { background:white; border:1px solid var(--line); border-radius:13px; padding:13px 15px 15px; margin-bottom:12px; box-shadow:0 3px 12px #222b4f04; overflow:hidden; }
    .molecule-top { display:flex; justify-content:space-between; gap:6px; align-items:center; margin-bottom:3px; font-size:10px; color:#8e93a5; }
    .molecule-top strong { color:#39425c; font-size:11px; }
    .molecule-image { display:flex; justify-content:center; align-items:center; height:145px; }
    .molecule-image svg { width:100%; height:145px; max-width:330px; }
    .molecule-smiles { font-family:monospace; font-size:10px; color:#9398aa; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin:4px 0 13px; }
    .molecule-properties { display:grid; grid-template-columns:repeat(3,1fr); gap:5px; border-top:1px solid #f0f1f6; padding-top:10px; }
    .molecule-properties span { display:block; font-size:8px; color:#a0a5b5; margin-bottom:4px; }
    .molecule-properties b { color:#65708a; font-size:11px; font-weight:650; }
    .section-label { font-size:9px; font-weight:750; letter-spacing:1.3px; color:#9a9fb0; margin:4px 0 10px; }
    .score { font-size:38px; letter-spacing:-1.5px; font-weight:750; color:#6854d8; }
    .app-footer { color:#a1a6b4; border-top:1px solid var(--line); margin-top:24px; padding-top:14px; font-size:10px; display:flex; justify-content:space-between; gap:10px; }
    @media(max-width:760px) { .hero { padding:19px; } .hero h1 { font-size:23px; } .topbar { flex-wrap:wrap; } .block-container { padding-left:1rem; padding-right:1rem; } }
    </style>""", unsafe_allow_html=True)


def pill(text: str, tone: str = "purple") -> str:
    return f'<span class="pill {tone}">{escape(text)}</span>'


def hero(title: str, description: str, badges: list[str]):
    st.markdown(f'<div class="hero"><div class="eyebrow">PCSK9 · CARDIOVASCULAR RESEARCH</div>'
                f'<h1>{escape(title)}</h1><p>{escape(description)}</p>'
                f'{"".join(pill(badge) for badge in badges)}</div>', unsafe_allow_html=True)


def stat(label, value, detail, color="#6854d8"):
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
