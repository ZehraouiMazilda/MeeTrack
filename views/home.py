import streamlit as st
import time
from datetime import datetime
from database import init_db, get_all_session_stats, get_conn

init_db()

def _delete_session(session_id):
    try:
        conn = get_conn()
        for table, col in [
            ("concentration_timeline", "session_id"),
            ("session_stats",         "session_id"),
            ("chat_messages",         "session_id"),
            ("voice_transcripts",     "session_id"),
            ("distraction_events",    "session_id"),
            ("notes",                 "session_id"),
            ("sources",               "session_id"),
            ("sessions",              "id"),
        ]:
            conn.execute(f"DELETE FROM {table} WHERE {col}=?", (session_id,))
        conn.commit()
        conn.close()
        print(f"[DB] Session {session_id} supprimée", flush=True)
        return True
    except Exception as e:
        print(f"[DB ERROR] delete_session: {e}", flush=True)
        return False

def _fmt_duration(secs):
    if not secs: return "—"
    mins = int(secs // 60)
    if mins < 60: return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h}h{m:02d}"

def _fmt_date(date_str):
    try:
        d = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%d %b %Y")
    except:
        return date_str[:10] if date_str else "—"

def _score_color(s):
    if not s: return "#7a6a9a"
    if s >= 70: return "#22c55e"
    if s >= 45: return "#f97316"
    return "#ef4444"

def show():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Space+Mono:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap');

    * { box-sizing: border-box; }

    /* Force Streamlit à se centrer proprement */
    .block-container {
        padding: 0 !important;
        max-width: 960px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    section[data-testid="stAppViewContainer"] { background: #0c0917; }

    /* Empêche les colonnes de s'étirer */
    [data-testid="column"] { min-width: 0 !important; }
    [data-testid="stHorizontalBlock"] { gap: 1rem !important; }

    /* Supprime les gaps Streamlit entre éléments */
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0 !important;
    }
    .element-container { margin: 0 !important; }
    iframe { display: block; }

    /* Full bleed */
    .full-bleed {
        width: 100vw;
        margin-left: calc(-50vw + 50%);
    }

    /* ── HEADER ─────────────────────────────────────────── */
    .lumi-header {
        background: rgba(12, 9, 23, 0.95);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid #1e1530;
        padding: 0 3rem;
        display: flex; align-items: center; justify-content: space-between;
        height: 60px;
    }
    .header-logo {
        font-family: 'Syne', sans-serif;
        font-size: 1.4rem; font-weight: 800;
        color: #f0eaff; letter-spacing: -0.03em;
        display: flex; align-items: center; gap: 10px;
    }
    .header-logo .logo-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #9b6dff;
        box-shadow: 0 0 8px #9b6dff;
        animation: glow 2s ease-in-out infinite;
    }
    @keyframes glow { 0%,100%{opacity:1;box-shadow:0 0 8px #9b6dff} 50%{opacity:0.4;box-shadow:0 0 3px #9b6dff} }
    .header-version {
        font-family: 'Space Mono', monospace;
        font-size: 0.68rem; color: #4a3560;
        letter-spacing: 0.1em;
    }

    /* ── HERO ───────────────────────────────────────────── */
    .hero-section {
        background: #0c0917;
        padding: 7rem 2rem 5rem;
        text-align: center;
        position: relative; overflow: hidden;
    }
    .hero-section::before {
        content: '';
        position: absolute; top: -20%; left: 50%;
        transform: translateX(-50%);
        width: 800px; height: 500px;
        background: radial-gradient(ellipse, rgba(155,109,255,0.08) 0%, transparent 65%);
        pointer-events: none;
    }
    .hero-eyebrow {
        font-family: 'Space Mono', monospace;
        font-size: 0.7rem; color: #9b6dff;
        letter-spacing: 0.2em; text-transform: uppercase;
        margin-bottom: 1.8rem;
    }
    .hero-title {
        font-family: 'Syne', sans-serif;
        font-size: clamp(2.8rem, 6vw, 5.5rem);
        font-weight: 800; line-height: 0.95;
        letter-spacing: -0.04em;
        color: #f0eaff;
        margin-bottom: 1rem;
        max-width: 700px;
        margin-left: auto; margin-right: auto;
    }
    .hero-title .line2 {
        display: block;
        background: linear-gradient(90deg, #9b6dff 0%, #c084fc 40%, #f472b6 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .hero-slogan {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 1.15rem; color: #7a6a9a;
        margin: 1.2rem auto 0; max-width: 480px;
        line-height: 1.7; font-weight: 400;
    }
    .hero-slogan strong { color: #b89aff; font-weight: 600; }

    /* ── DIVIDER ─────────────────────────────────────────── */
    .divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, #2d2040 30%, #2d2040 70%, transparent);
        max-width: 960px; margin: 0 auto;
    }

    /* ── SECTION ─────────────────────────────────────────── */
    .section {
        padding: 3rem 0;
        max-width: 960px;
        margin: 0 auto;
    }
    .section-eyebrow {
        font-family: 'Space Mono', monospace;
        font-size: 0.65rem; color: #9b6dff;
        letter-spacing: 0.2em; text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .section-heading {
        font-family: 'Syne', sans-serif;
        font-size: 2rem; font-weight: 800;
        color: #f0eaff; letter-spacing: -0.03em;
        margin-bottom: 1.5rem;
    }

    /* ── HOW STEPS ───────────────────────────────────────── */
    .step-card {
        background: #13101e;
        border: 1px solid #1e1530;
        border-radius: 20px;
        padding: 2rem 1.8rem;
        height: 100%;
        transition: border-color 0.25s, transform 0.25s;
        position: relative;
    }
    .step-card:hover {
        border-color: rgba(155,109,255,0.5);
        transform: translateY(-4px);
    }
    .step-num {
        font-family: 'Space Mono', monospace;
        font-size: 0.6rem; color: #5a4a7a;
        letter-spacing: 0.15em; margin-bottom: 1.2rem;
    }
    .step-icon {
        font-size: 1.6rem; margin-bottom: 0.8rem;
        display: block;
    }
    .step-title {
        font-family: 'Syne', sans-serif;
        font-size: 1rem; font-weight: 700;
        color: #e0d8ff; margin-bottom: 0.5rem;
    }
    .step-desc {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.82rem; color: #5a4a7a;
        line-height: 1.65;
    }

    /* ── FEATURES PILLS ──────────────────────────────────── */
    .pills-wrap {
        display: flex; flex-wrap: wrap;
        gap: 10px; margin-top: 0.5rem;
    }
    .pill {
        background: #13101e;
        border: 1px solid #1e1530;
        border-radius: 99px;
        padding: 7px 18px;
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.82rem; font-weight: 600;
        color: #9b6dff;
        transition: border-color 0.2s, background 0.2s;
    }
    .pill:hover { background: #1e1530; border-color: #4a3560; }

    /* Bouton Supprimer — discret rouge */
    button[kind="secondary"]:last-child {
        background: transparent !important;
        border: 1px solid #3d1f1f !important;
        color: #7a4040 !important;
    }
    button[kind="secondary"]:last-child:hover {
        border-color: #ef4444 !important;
        color: #ef4444 !important;
    }

    /* ── SESSION CARDS ───────────────────────────────────── */
    .sess-card {
        background: #13101e;
        border: 1px solid #2d2040;
        border-radius: 14px;
        padding: 1.1rem 1.4rem;
        position: relative;
        transition: border-color 0.25s;
        margin-bottom: 0;
    }
    .sess-card:hover { border-color: rgba(155,109,255,0.5); }
    .sess-title {
        font-family: 'Syne', sans-serif;
        font-size: 0.95rem; font-weight: 700;
        color: #e0d8ff; margin-bottom: 4px;
        padding-right: 56px;
    }
    .sess-summary {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.78rem; color: #5a4a7a;
        line-height: 1.5; margin-bottom: 8px;
        display: -webkit-box; -webkit-line-clamp: 1;
        -webkit-box-orient: vertical; overflow: hidden;
    }
    .sess-meta {
        font-family: 'Space Mono', monospace;
        font-size: 0.72rem; color: #6a5a8a;
        display: flex; gap: 16px; flex-wrap: wrap;
    }
    .sess-score {
        position: absolute; top: 1rem; right: 1.2rem;
        font-family: 'Syne', sans-serif;
        font-size: 1.2rem; font-weight: 800;
    }
    .empty-wrap {
        text-align: center; padding: 4rem 2rem;
        border: 1px dashed #1e1530; border-radius: 20px;
    }
    .empty-title {
        font-family: 'Syne', sans-serif;
        font-size: 1.1rem; font-weight: 700;
        color: #2d2040; margin-bottom: 0.5rem;
    }
    .empty-sub {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.85rem; color: #1e1530;
    }

    /* ── NEW SESSION ─────────────────────────────────────── */
    .new-sess-section {
        background: #0e0b1a;
        border-top: 1px solid #1e1530;
        padding: 4rem 0;
        text-align: center;
    }

    /* ── FOOTER ──────────────────────────────────────────── */
    .lumi-footer {
        background: #080613;
        border-top: 1px solid #13101e;
        padding: 4rem 2rem 2.5rem;
    }
    .footer-cols {
        display: grid;
        grid-template-columns: 2fr 1fr 1fr;
        gap: 3rem; margin-bottom: 3rem; max-width: 960px; margin-left: auto; margin-right: auto;
    }
    .footer-logo {
        font-family: 'Syne', sans-serif;
        font-size: 1.5rem; font-weight: 800;
        color: #f0eaff; margin-bottom: 0.8rem;
    }
    .footer-tagline {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.85rem; color: #5a4a7a;
        line-height: 1.8; max-width: 280px;
    }
    .footer-col-label {
        font-family: 'Space Mono', monospace;
        font-size: 0.6rem; color: #7a6a9a;
        letter-spacing: 0.2em; text-transform: uppercase;
        margin-bottom: 1rem;
    }
    .footer-item {
        font-family: 'Bricolage Grotesque', sans-serif;
        font-size: 0.82rem; color: #5a4a7a;
        margin-bottom: 0.6rem;
    }
    .footer-bottom {
        border-top: 1px solid #13101e;
        padding-top: 2rem;
        display: flex; justify-content: space-between;
        align-items: center; flex-wrap: wrap; gap: 1rem;
    }
    .footer-copy {
        font-family: 'Space Mono', monospace;
        font-size: 0.62rem; color: #5a4a7a;
    }
    .footer-tags { display: flex; gap: 6px; flex-wrap: wrap; }
    .footer-tag {
        background: #0e0b1a; border: 1px solid #2d2040;
        border-radius: 6px; padding: 3px 10px;
        font-family: 'Space Mono', monospace;
        font-size: 0.6rem; color: #5a4a7a;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── HEADER ──────────────────────────────────────────────
    st.markdown("""
    <div class="lumi-header full-bleed">
        <div class="header-logo">
            <div class="logo-dot"></div>
            Lumi
        </div>
        <div class="header-version">v1.0 &nbsp;·&nbsp; Master SISE 2025</div>
    </div>
    """, unsafe_allow_html=True)

    # ── HERO ────────────────────────────────────────────────
    st.markdown("""
    <div class="hero-section full-bleed">
        <div class="hero-eyebrow">Assistant d'étude intelligent</div>
        <div class="hero-title">
            Ton cerveau mérite<br>
            <span class="line2">mieux que du café.</span>
        </div>
        <div class="hero-slogan">
            Lumi surveille ta concentration, répond à tes questions à voix haute
            et transforme tes sessions d'étude en <strong>vraie progression</strong>.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="divider full-bleed"></div>', unsafe_allow_html=True)

    # ── HOW IT WORKS ────────────────────────────────────────
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="section-eyebrow">Mode d\'emploi</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Comment ça marche ?</div>', unsafe_allow_html=True)

    steps = [
        ("01", "📄", "Upload tes cours",
         "Glisse tes PDF ou fichiers texte. Lumi lit et comprend tes documents."),
        ("02", "🎤", "Dis « Lumi »",
         "Active l'assistant vocal, pose ta question. Il répond à voix haute."),
        ("03", "📷", "Active la caméra",
         "Lumi surveille tes yeux, l'orientation de ta tête et les distractions."),
        ("04", "📝", "Prends des notes",
         "Écris tes notes brutes, Lumi les corrige automatiquement."),
        ("05", "📊", "Consulte tes stats",
         "Score de concentration, alertes, conversation — tout est sauvegardé."),
        ("06", "🏁", "Quitte proprement",
         "Clique Quitter pour sauvegarder et voir les analytics de session."),
    ]

    cols1 = st.columns(3, gap="large")
    for i, (num, icon, title, desc) in enumerate(steps[:3]):
        with cols1[i]:
            st.markdown(f"""
            <div class="step-card">
                <div class="step-num">ETAPE {num}</div>
                <span class="step-icon">{icon}</span>
                <div class="step-title">{title}</div>
                <div class="step-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)

    cols2 = st.columns(3, gap="large")
    for i, (num, icon, title, desc) in enumerate(steps[3:]):
        with cols2[i]:
            st.markdown(f"""
            <div class="step-card">
                <div class="step-num">ETAPE {num}</div>
                <span class="step-icon">{icon}</span>
                <div class="step-title">{title}</div>
                <div class="step-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="divider full-bleed"></div>', unsafe_allow_html=True)

    # ── FEATURES ────────────────────────────────────────────
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="section-eyebrow">Fonctionnalités</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Tout ce que Lumi fait</div>', unsafe_allow_html=True)

    features = [
        "Wake word vocal",
        "Détection clignements",
        "Analyse orientation tête",
        "Score concentration temps réel",
        "Chat IA contextuel",
        "Réponses vocales",
        "Lecture PDF",
        "Correction de notes",
        "Timeline concentration",
        "Alertes intelligentes",
        "Sauvegarde session",
        "Analytics détaillés",
    ]
    st.markdown(
        '<div class="pills-wrap">' +
        "".join(f'<span class="pill">{f}</span>' for f in features) +
        '</div>',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="divider full-bleed"></div>', unsafe_allow_html=True)

    # ── SESSIONS ────────────────────────────────────────────
    st.markdown('<div class="section">', unsafe_allow_html=True)
    st.markdown('<div class="section-eyebrow" style="text-align:center;">Historique</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading" style="text-align:center;">Mes sessions</div>', unsafe_allow_html=True)

    sessions = get_all_session_stats()

    if sessions:
        for i in range(0, len(sessions), 2):
            cols = st.columns(2, gap="large")
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(sessions): break
                s = sessions[idx]
                score = s.get("score_avg") or 0
                sc = _score_color(score)
                summary = s.get("summary") or s.get("theme") or "Pas de résumé disponible."
                with col:
                    st.markdown(f"""
                    <div class="sess-card">
                        <div class="sess-score" style="color:{sc};">{int(score)}%</div>
                        <div class="sess-title">{s['title']}</div>
                        <div class="sess-summary">{summary}</div>
                        <div class="sess-meta">
                            <span>{_fmt_date(s.get('created_at',''))}</span>
                            <span>{_fmt_duration(s.get('duration_sec',0))}</span>
                            <span>{s.get('sources_count',0)} source(s)</span>
                            <span>{s.get('lumi_calls',0)}x Lumi</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    ba, bb = st.columns([1, 1])
                    with ba:
                        if st.button("Voir les stats", key=f"stats_{s['id']}", use_container_width=True):
                            st.session_state["selected_session_id"] = s["id"]
                            st.session_state["page"] = "analytics"
                            st.rerun()
                    with bb:
                        if st.button("Supprimer", key=f"del_{s['id']}", use_container_width=True):
                            st.session_state[f"confirm_del_{s['id']}"] = True
                            st.rerun()
                    if st.session_state.get(f"confirm_del_{s['id']}"):
                        st.warning(f"Supprimer **{s['title']}** ? Cette action est irréversible.")
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("Oui, supprimer", key=f"yes_{s['id']}", use_container_width=True):
                                ok = _delete_session(s["id"])
                                st.session_state.pop(f"confirm_del_{s['id']}", None)
                                if ok:
                                    st.success("Session supprimée !")
                                    time.sleep(0.5)
                                st.rerun()
                        with cb:
                            if st.button("Annuler", key=f"no_{s['id']}", use_container_width=True):
                                st.session_state.pop(f"confirm_del_{s['id']}", None)
                                st.rerun()
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-wrap">
            <div class="empty-title">Aucune session pour l'instant</div>
            <div class="empty-sub">Lance ta première session ci-dessous pour commencer.</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── NOUVELLE SESSION ────────────────────────────────────
    st.markdown('<div class="new-sess-section full-bleed">', unsafe_allow_html=True)
    st.markdown('<div class="section-eyebrow" style="text-align:center;">Nouvelle session</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-heading" style="text-align:center;margin-bottom:2rem;">Prêt à étudier ?</div>', unsafe_allow_html=True)

    _, form_col, _ = st.columns([1, 2, 1])
    with form_col:
        title_input = st.text_input(
            "", placeholder="Nom de la session  —  ex: Révision Algo S2",
            label_visibility="collapsed", key="new_session_name"
        )
        can_start = bool(title_input.strip())
        if st.button(
            "Lancer la session" if can_start else "Entre un nom pour démarrer",
            key="start_session", use_container_width=True,
            disabled=not can_start
        ):
            st.session_state["new_session_title"] = title_input.strip()
            st.session_state["session_id"] = None
            st.session_state["page"] = "session"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ── FOOTER ──────────────────────────────────────────────
    st.markdown("""
    <div class="lumi-footer full-bleed">
        <div class="footer-cols">
            <div>
                <div class="footer-logo">Lumi</div>
                <div class="footer-tagline">
                    Assistant d'étude intelligent conçu pour t'aider à rester concentré,
                    poser tes questions à voix haute et analyser tes sessions de révision.
                </div>
            </div>
            <div>
                <div class="footer-col-label">Stack technique</div>
                <div class="footer-item">Streamlit</div>
                <div class="footer-item">Groq API</div>
                <div class="footer-item">Llama 3.1</div>
                <div class="footer-item">Whisper Large v3</div>
                <div class="footer-item">MediaPipe</div>
            </div>
            <div>
                <div class="footer-col-label">Fonctions clés</div>
                <div class="footer-item">Détection concentration</div>
                <div class="footer-item">Réponses vocales TTS</div>
                <div class="footer-item">Lecture PDF</div>
                <div class="footer-item">Analytics session</div>
                <div class="footer-item">Sauvegarde complète</div>
            </div>
        </div>
        <div class="footer-bottom">
            <div class="footer-copy">2025–2026 · Master SISE · Fait avec soin</div>
            <div class="footer-tags">
                <span class="footer-tag">Python 3.10</span>
                <span class="footer-tag">SQLite</span>
                <span class="footer-tag">gTTS</span>
                <span class="footer-tag">OpenCV</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)