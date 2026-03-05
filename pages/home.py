import streamlit as st
from database import create_meeting, get_meeting_by_code, join_meeting, get_user_meetings
from datetime import datetime

def show():
    user = st.session_state.user

    # ── Header ────────────────────────────────────────────────
    col_logo, col_right = st.columns([3, 1])
    with col_logo:
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:12px; padding: 1rem 0 0.5rem;">
            <div style="font-family:'Syne',sans-serif; font-size:1.6rem; font-weight:800;">
                Meet<span style="background:linear-gradient(135deg,#4f6ef7,#7c3aed);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">Track</span>
            </div>
            <div style="color:#64748b; font-size:0.85rem; padding-top:4px;">
                Bonjour, <b style="color:#e2e8f0;">{user['username']}</b> 👋
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_right:
        st.markdown("<div style='padding-top:1rem'>", unsafe_allow_html=True)
        if st.button("🚪 Déconnexion"):
            st.session_state.user = None
            st.session_state.page = "auth"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Actions ───────────────────────────────────────────────
    left, right = st.columns(2)

    with left:
        st.markdown("""
        <div class="card">
            <div class="card-title">🚀 Créer une réunion</div>
        </div>
        """, unsafe_allow_html=True)
        meeting_name = st.text_input(
            "Nom de la réunion",
            placeholder="ex: Sprint Review, Daily Standup...",
            key="new_meeting_name"
        )
        if st.button("✨ Créer et démarrer", key="btn_create"):
            if not meeting_name.strip():
                st.error("Donne un nom à ta réunion.")
            else:
                meeting = create_meeting(meeting_name.strip(), user["id"])
                join_meeting(meeting["id"], user["id"])
                st.session_state.meeting = meeting
                st.session_state.is_creator = True
                st.session_state.page = "meeting"
                st.rerun()

    with right:
        st.markdown("""
        <div class="card">
            <div class="card-title">🔗 Rejoindre une réunion</div>
        </div>
        """, unsafe_allow_html=True)
        code_input = st.text_input(
            "Code de la réunion",
            placeholder="ex: ABC123",
            key="join_code",
            max_chars=6
        ).upper().strip()
        if st.button("➡️ Rejoindre", key="btn_join"):
            if not code_input or len(code_input) != 6:
                st.error("Le code doit faire 6 caractères.")
            else:
                meeting = get_meeting_by_code(code_input)
                if not meeting:
                    st.error("Code introuvable. Vérifie et réessaie.")
                elif meeting["status"] == "ended":
                    st.error("Cette réunion est terminée.")
                else:
                    join_meeting(meeting["id"], user["id"])
                    st.session_state.meeting = meeting
                    st.session_state.is_creator = (meeting["creator_id"] == user["id"])
                    st.session_state.page = "meeting"
                    st.rerun()

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # ── History preview ───────────────────────────────────────
    meetings = get_user_meetings(user["id"])
    if meetings:
        st.markdown("<hr>", unsafe_allow_html=True)
        head_col, btn_col = st.columns([4, 1])
        with head_col:
            st.markdown('<div class="card-title">📋 Réunions récentes</div>', unsafe_allow_html=True)
        with btn_col:
            if st.button("Voir tout →", key="btn_history"):
                st.session_state.page = "history"
                st.rerun()

        for m in meetings[:4]:
            dt = datetime.fromisoformat(m["created_at"])
            role = "👑 Créateur" if m["creator_id"] == user["id"] else "👤 Participant"
            status_color = "#22d3a0" if m["status"] == "active" else "#64748b"
            status_label = "En cours" if m["status"] == "active" else "Terminée"

            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"""
                <div style="padding: 10px 0; border-bottom: 1px solid #1e2540;">
                    <div style="font-weight:600; color:#e2e8f0; font-size:0.95rem;">{m['name']}</div>
                    <div style="font-size:0.75rem; color:#64748b; margin-top:2px;">
                        {dt.strftime('%d/%m/%Y %H:%M')} · {role} ·
                        <span style="color:{status_color};">{status_label}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style="padding:10px 0; text-align:center;">
                    <div style="font-family:'Syne',sans-serif; font-size:0.8rem; font-weight:700;
                                color:#4f6ef7; letter-spacing:0.1em;">{m['code']}</div>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                if st.button("Détails", key=f"detail_{m['id']}"):
                    st.session_state.selected_meeting_id = m["id"]
                    st.session_state.page = "history"
                    st.rerun()