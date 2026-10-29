"""Custom surfaces inherit Streamlit's live color-scheme from its native theme.

Keep native widget/table/chart palettes in .streamlit/config.toml. CSS color
pairs update immediately when the browser switches appearance, without relying
on Python's potentially stale st.context.theme value during that transition.
"""

GRAPHITE_STYLE = """<style>
.stApp {
    --lab-bg:light-dark(#f3f6f8,#13191f);
    --lab-surface:light-dark(#ffffff,#1b232c);
    --lab-rail:light-dark(#eaf0f3,#171f27);
    --lab-ink:light-dark(#243542,#e8edf2);
    --lab-muted:light-dark(#526977,#a6b6c3);
    --lab-accent:light-dark(#087e83,#7be4d1);
    --lab-on-accent:light-dark(#ffffff,#102b27);
    --lab-soft:light-dark(#e1efef,#263b3b);
    --lab-line:light-dark(#d5dfe5,#35414d);
    --lab-green:light-dark(#216c50,#89d8b3);
    --lab-green-bg:light-dark(#e7f3ed,#223b32);
    --lab-amber:light-dark(#815e17,#efcb79);
    --lab-amber-bg:light-dark(#faf0da,#3d3423);
    --lab-rose:light-dark(#9b3e50,#f3a0b0);
    --lab-rose-bg:light-dark(#faeaf0,#412a34);
    color:var(--lab-ink);
}
.block-container { padding:3.5rem 1.5rem 2rem; max-width:1600px; }
[data-testid="stSidebar"] { min-width:235px; max-width:235px; }
[data-testid="stSidebar"] [data-testid="stSidebarContent"] { padding-top:.8rem; }
[data-testid="stSidebarHeader"] { height:30px; margin-bottom:5px; }
[data-testid="stSidebar"] hr { margin:1rem 0; border-color:var(--lab-line); }
[data-testid="stSidebar"] [data-testid="stRadio"] { gap:2px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding:7px 9px; border-radius:5px; margin:0; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) { background:var(--lab-soft); }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color:var(--lab-accent); }
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size:13px; }
.brand { display:flex; align-items:center; gap:9px; margin:0; }
.brand-mark { background:var(--lab-accent); color:var(--lab-on-accent); border-radius:7px; padding:6px 8px; font-size:17px; font-weight:700; }
.brand-name { font-size:19px; line-height:1.2; font-weight:600; letter-spacing:-.6px; white-space:nowrap; }
.brand-caption { font-size:11px; color:var(--lab-muted); margin-top:3px; }
.nav-caption { color:var(--lab-muted); font-size:11px; letter-spacing:1.1px; font-weight:600; margin:14px 0 6px; }
.sidebar-note { background:var(--lab-soft); border:1px solid var(--lab-line); padding:12px; border-radius:7px; font-size:12px; color:var(--lab-muted); line-height:1.6; }
.sidebar-note strong { color:var(--lab-ink); display:block; margin-bottom:4px; }
.st-key-studio_header { background:var(--lab-rail); border-bottom:1px solid var(--lab-line); padding:12px 14px; border-radius:7px 7px 0 0; margin-bottom:8px; }
.st-key-studio_header [data-testid="stPills"] { margin:0; }
.st-key-studio_header button { border-radius:5px; }
.topbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:2px 0 18px; flex-wrap:wrap; }
.breadcrumb { font-size:12px; color:var(--lab-muted); }
.breadcrumb strong { color:var(--lab-ink); margin-left:9px; font-weight:500; }
.topbadges { display:flex; gap:7px; flex-wrap:wrap; }
.pill { display:inline-flex; align-items:center; gap:5px; background:var(--lab-surface); border:1px solid var(--lab-line); border-radius:4px; padding:4px 8px; font-size:11px; font-weight:500; color:var(--lab-muted); }
.pill.purple,.pill.teal { background:var(--lab-soft); color:var(--lab-accent); }
.pill.green { background:var(--lab-green-bg); color:var(--lab-green); }
.pill.amber { background:var(--lab-amber-bg); color:var(--lab-amber); }
.pill.rose { background:var(--lab-rose-bg); color:var(--lab-rose); }
.hero { border-bottom:1px solid var(--lab-line); padding:4px 0 20px; margin-bottom:20px; }
.eyebrow { font-size:11px; letter-spacing:1.3px; color:var(--lab-accent); font-weight:500; margin-bottom:8px; }
.hero h1 { margin:0 0 9px; padding:0!important; font-size:30px; line-height:1.2; font-weight:600; letter-spacing:-.8px; color:var(--lab-ink); }
.hero p { color:var(--lab-muted); font-size:14px; line-height:1.6; margin:0 0 14px; max-width:880px; }
.hero .pill { margin:0 6px 5px 0; }
.stat-card { background:var(--lab-surface); border:1px solid var(--lab-line); border-radius:7px; padding:16px 18px; min-height:116px; margin-bottom:12px; }
.stat-label { font-size:11px; color:var(--lab-muted); font-weight:500; }
.stat-value { font-size:30px; font-weight:600; letter-spacing:-1px; margin:5px 0 3px; line-height:1.2; color:var(--lab-accent); font-variant-numeric:tabular-nums; }
.stat-detail { font-size:12px; color:var(--lab-muted); }
[data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][style*="border"],
[class*="st-key-panel_"] { border-color:var(--lab-line)!important; border-radius:7px!important; background:var(--lab-surface); }
[data-testid="stForm"] { border:0; padding:0; }
[data-testid="stExpander"] { background:var(--lab-surface); border-color:var(--lab-line); border-radius:7px; }
h2 { font-size:21px!important; letter-spacing:-.4px; }
h3 { font-size:16px!important; letter-spacing:-.2px; }
[data-testid="stCaptionContainer"] p { font-size:12px; line-height:1.6; color:var(--lab-muted)!important; }
.stButton button,.stDownloadButton button,.stLinkButton a,.stFormSubmitButton button { border-radius:5px; font-size:13px; font-weight:500; }
.stButton button[kind^="primary"],.stFormSubmitButton button[kind^="primary"] { background:var(--lab-accent); color:var(--lab-on-accent); border-color:var(--lab-accent); box-shadow:none; }
.stButton button[kind^="primary"] p,.stFormSubmitButton button[kind^="primary"] p { color:inherit; }
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input { font-size:14px; border-radius:5px; }
.molecule-card { background:var(--lab-surface); border:1px solid var(--lab-line); border-radius:7px; padding:13px 15px 15px; margin-bottom:12px; overflow:hidden; }
.molecule-top { display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:10px; font-size:12px; color:var(--lab-muted); }
.molecule-top strong { color:var(--lab-ink); font-size:13px; }
/* Preserve original element colors and bonds on a white chemistry drawing sheet. */
.molecule-image { display:flex; justify-content:center; align-items:center; height:155px; background:#fff; border-radius:5px; }
.molecule-image svg { width:100%; height:145px; max-width:330px; }
.molecule-smiles { font-family:monospace; font-size:12px; color:var(--lab-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin:10px 0 13px; }
.molecule-properties { display:grid; grid-template-columns:repeat(3,1fr); gap:5px; border-top:1px solid var(--lab-line); padding-top:10px; }
.molecule-properties span { display:block; font-size:11px; color:var(--lab-muted); margin-bottom:4px; }
.molecule-properties b { color:var(--lab-ink); font-size:13px; font-weight:500; }
.section-label { font-size:11px; font-weight:500; letter-spacing:1px; color:var(--lab-muted); margin:4px 0 10px; }
.score { font-size:38px; letter-spacing:-1px; font-weight:600; color:var(--lab-accent); }
.studio-empty { min-height:190px; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:10px; background:radial-gradient(circle,var(--lab-line) .65px,transparent .8px); background-size:18px 18px; border:1px solid var(--lab-line); border-radius:7px; color:var(--lab-muted); padding:24px; text-align:center; }
.studio-empty strong { color:var(--lab-ink); font-size:15px; font-weight:500; background:var(--lab-surface); padding:3px 8px; }
.studio-empty span { font-size:13px; background:var(--lab-surface); padding:3px 8px; }
.app-footer { color:var(--lab-muted); border-top:1px solid var(--lab-line); margin-top:24px; padding-top:14px; font-size:12px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; }
@media(max-width:760px) {
    .hero h1 { font-size:25px; }
    .block-container { padding-left:1rem; padding-right:1rem; }
    .st-key-studio_header [data-testid="stHorizontalBlock"] { flex-direction:column; }
    .st-key-studio_header [data-testid="stColumn"] { width:100%; flex:1 1 auto; }
}
@media(pointer:coarse) { [data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input { font-size:16px; } }
</style>"""
