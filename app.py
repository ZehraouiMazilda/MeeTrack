import streamlit as st
from database import init_db

st.set_page_config(
    page_title="MeeTrack",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

init_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --bg:       #08090f;
    --surface:  #0f1120;
    --surface2: #151828;
    --border:   #1e2540;
    --accent:   #4f6ef7;
    --accent2:  #7c3aed;
    --green:    #22d3a0;
    --orange:   #f59e0b;
    --red:      #ef4444;
    --text:     #e2e8f0;
    --muted:    #64748b;
    --radius:   14px;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: 'DM Sans', sans-serif;
    color: var(--text);
}
[data-testid="stAppViewContainer"] > .main { background: var(--bg) !important; }
[data-testid="stSidebar"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.6rem 1.4rem !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 24px rgba(79,110,247,0.3) !important;
}

/* ── Danger button ── */
.btn-danger > button {
    background: linear-gradient(135deg, #ef4444, #b91c1c) !important;
}

/* ── Cards ── */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
}
.card-title {
    font-family: 'Syne', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.8rem;
}

/* ── Inputs ── */
div[data-baseweb="input"] input,
div[data-baseweb="select"] > div,
.stTextInput input,
.stTextArea textarea {
    background: var(--surface2) !important;
    border-color: var(--border) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Progress bar ── */
.prog-bg {
    background: var(--border);
    border-radius: 99px;
    height: 7px;
    overflow: hidden;
    margin-top: 5px;
}
.prog-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.4s ease;
}

/* ── Metric ── */
.metric-val {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 800;
    line-height: 1;
    color: var(--accent);
}
.metric-lbl {
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 3px;
}

/* ── Alert ── */
.alert-box {
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.4);
    border-radius: 10px;
    padding: 12px 16px;
    color: #fca5a5;
    font-size: 0.88rem;
    margin: 6px 0;
    font-family: 'Syne', sans-serif;
}
.ok-box {
    background: rgba(34,211,160,0.08);
    border: 1px solid rgba(34,211,160,0.3);
    border-radius: 10px;
    padding: 12px 16px;
    color: #6ee7b7;
    font-size: 0.88rem;
    margin: 6px 0;
}

/* ── Live dot ── */
.dot-live {
    display: inline-block;
    width: 8px; height: 8px;
    background: var(--red);
    border-radius: 50%;
    animation: blink 1.2s infinite;
    margin-right: 6px;
    vertical-align: middle;
}
@keyframes blink {
    0%,100% { opacity:1; } 50% { opacity:0.3; }
}

/* ── Speaker pill ── */
.pill {
    display: inline-block;
    background: rgba(79,110,247,0.15);
    border: 1px solid rgba(79,110,247,0.3);
    border-radius: 99px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--accent);
    margin-right: 6px;
    font-family: 'Syne', sans-serif;
}

/* ── Transcript box ── */
.transcript-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem;
    max-height: 180px;
    overflow-y: auto;
    font-size: 0.88rem;
    line-height: 1.7;
}
.transcript-line {
    padding: 4px 0;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}
.transcript-line:last-child { border-bottom: none; }

/* ── Tab style ── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--surface) !important;
    border-radius: 10px !important;
    padding: 4px !important;
    gap: 4px !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--muted) !important;
    border-radius: 8px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
    color: white !important;
}

/* ── Chat ── */
.chat-msg-user {
    background: linear-gradient(135deg, rgba(79,110,247,0.15), rgba(124,58,237,0.15));
    border: 1px solid rgba(79,110,247,0.2);
    border-radius: 12px 12px 4px 12px;
    padding: 10px 14px;
    margin: 6px 0 6px 20%;
    font-size: 0.88rem;
}
.chat-msg-ai {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px 12px 12px 4px;
    padding: 10px 14px;
    margin: 6px 20% 6px 0;
    font-size: 0.88rem;
}

/* ── Summary box ── */
.summary-box {
    background: linear-gradient(135deg, rgba(79,110,247,0.06), rgba(124,58,237,0.06));
    border: 1px solid rgba(79,110,247,0.2);
    border-radius: var(--radius);
    padding: 1.2rem 1.4rem;
    font-size: 0.9rem;
    line-height: 1.8;
    white-space: pre-wrap;
}

/* ── Code badge ── */
.code-badge {
    font-family: 'Syne', sans-serif;
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: 0.3em;
    color: var(--accent);
    background: rgba(79,110,247,0.1);
    border: 2px dashed rgba(79,110,247,0.4);
    border-radius: 12px;
    padding: 16px 32px;
    text-align: center;
    margin: 12px 0;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 0.8rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────
for key, val in {
    "page": "auth",
    "user": None,
    "meeting": None,
    "is_creator": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ── Routing ───────────────────────────────────────────────────
page = st.session_state.page

if page == "auth":
    from pages.auth import show
    show()
elif page == "home":
    from pages.home import show
    show()
elif page == "meeting":
    from pages.meeting import show
    show()
elif page == "history":
    from pages.history import show
    show()