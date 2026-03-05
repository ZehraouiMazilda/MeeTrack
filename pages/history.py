import streamlit as st
import json
import time
import numpy as np
from datetime import datetime
import plotly.graph_objects as go

from database import (
    get_user_meetings, get_meeting_by_id, get_meeting_transcripts,
    get_meeting_participants, get_distraction_events, get_speech_times,
    get_summary, save_summary
)
from services.llm import generate_summary, get_participant_themes, chatbot_response

COLORS = ["#4f6ef7","#22d3a0","#f59e0b","#ef4444","#7c3aed","#ec4899","#06b6d4"]

def _fmt(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def _score_color(s):
    if s > 60: return "#22d3a0"
    if s > 30: return "#f59e0b"
    return "#ef4444"


def show():
    user = st.session_state.user

    # ── Header ────────────────────────────────────────────────
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown("""
        <div style="font-family:'Syne',sans-serif; font-size:1.6rem; font-weight:800; padding:1rem 0 0.2rem;">
            📋 Historique des réunions
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("<div style='padding-top:1rem'>", unsafe_allow_html=True)
        if st.button("🏠 Accueil"):
            st.session_state.page = "home"
            st.session_state.pop("selected_meeting_id", None)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    meetings = get_user_meetings(user["id"])

    if not meetings:
        st.info("Aucune réunion pour l'instant. Crée ou rejoins une réunion depuis l'accueil !")
        return

    # ── Meeting selector ──────────────────────────────────────
    selected_id = st.session_state.get("selected_meeting_id", None)

    # Sidebar-like list
    list_col, detail_col = st.columns([1, 3])

    with list_col:
        st.markdown('<div class="card-title">Réunions</div>', unsafe_allow_html=True)
        for m in meetings:
            dt = datetime.fromisoformat(m["created_at"])
            role = "👑" if m["creator_id"] == user["id"] else "👤"
            active = selected_id == m["id"]
            bg = "rgba(79,110,247,0.15)" if active else "transparent"
            border = "1px solid rgba(79,110,247,0.4)" if active else "1px solid #1e2540"

            st.markdown(f"""
            <div style="background:{bg}; border:{border}; border-radius:10px;
                        padding:10px 12px; margin-bottom:6px; cursor:pointer;">
                <div style="font-weight:600; font-size:0.88rem; color:#e2e8f0;">{role} {m['name']}</div>
                <div style="font-size:0.72rem; color:#64748b; margin-top:2px;">
                    {dt.strftime('%d/%m %H:%M')} ·
                    <span style="color:{'#22d3a0' if m['status']=='active' else '#475569'};">
                        {'En cours' if m['status']=='active' else 'Terminée'}
                    </span>
                </div>
            </div>""", unsafe_allow_html=True)

            if st.button(f"Ouvrir", key=f"open_{m['id']}"):
                st.session_state.selected_meeting_id = m["id"]
                st.session_state.pop("chat_history", None)
                st.rerun()

    # ── Meeting detail ────────────────────────────────────────
    with detail_col:
        if not selected_id:
            st.markdown("""
            <div style="text-align:center; padding:4rem; color:#475569;">
                <div style="font-size:2rem; margin-bottom:1rem;">👈</div>
                <div>Sélectionne une réunion pour voir les détails</div>
            </div>""", unsafe_allow_html=True)
            return

        meeting     = get_meeting_by_id(selected_id)
        if not meeting:
            st.error("Réunion introuvable.")
            return

        transcript  = get_meeting_transcripts(selected_id)
        participants = get_meeting_participants(selected_id)
        is_creator  = meeting["creator_id"] == user["id"]
        summary_row = get_summary(selected_id)

        # Durée
        start = datetime.fromisoformat(meeting["created_at"])
        end   = datetime.fromisoformat(meeting["ended_at"]) if meeting["ended_at"] else datetime.now()
        duration_sec = (end - start).total_seconds()

        # ── KPIs ──
        k1, k2, k3, k4 = st.columns(4)
        for col, icon, val, lbl in [
            (k1, "⏱", _fmt(duration_sec), "Durée"),
            (k2, "👥", str(len(participants)), "Participants"),
            (k3, "💬", str(len(transcript)), "Échanges"),
            (k4, "🏷️", meeting["code"], "Code"),
        ]:
            with col:
                st.markdown(f"""
                <div class="card" style="text-align:center; padding:0.9rem 0.5rem;">
                    <div style="font-size:1.2rem;">{icon}</div>
                    <div style="font-family:'Syne',sans-serif; font-size:1.4rem; font-weight:800;
                                color:#4f6ef7; margin:3px 0;">{val}</div>
                    <div style="font-size:0.72rem; color:#64748b;">{lbl}</div>
                </div>""", unsafe_allow_html=True)

        # ── Tabs ──────────────────────────────────────────────
        tab_sum, tab_chat, tab_stats = st.tabs(["✨ Résumé", "💬 Chatbot", "📊 Statistiques"])

        # ────────────────────────────────────────────────────
        # TAB 1 : RÉSUMÉ
        # ────────────────────────────────────────────────────
        with tab_sum:
            if not summary_row:
                if st.button("🧠 Générer le résumé avec Claude", use_container_width=True):
                    with st.spinner("Claude analyse la réunion…"):
                        result = generate_summary(transcript, participants, meeting["name"], duration_sec)
                        save_summary(selected_id, result["summary"],
                                     result.get("tasks","[]"), result.get("themes","[]"))
                        st.rerun()
            else:
                st.markdown('<div class="card-title">🎯 Résumé exécutif</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="summary-box">{summary_row["summary_text"]}</div>',
                            unsafe_allow_html=True)

                # Thèmes
                try:
                    themes = json.loads(summary_row["themes"]) if summary_row["themes"] else []
                except:
                    themes = []
                if themes:
                    st.markdown('<div class="card-title" style="margin-top:1rem;">🏷️ Thèmes abordés</div>',
                                unsafe_allow_html=True)
                    pills = " ".join(f'<span class="pill">{t}</span>' for t in themes)
                    st.markdown(f"<div>{pills}</div>", unsafe_allow_html=True)

                # Tâches
                try:
                    tasks = json.loads(summary_row["tasks"]) if summary_row["tasks"] else []
                except:
                    tasks = []
                if tasks:
                    st.markdown('<div class="card-title" style="margin-top:1rem;">✅ Actions à mener</div>',
                                unsafe_allow_html=True)
                    for t in tasks:
                        st.markdown(f"""
                        <div style="background:#151828; border:1px solid #1e2540; border-radius:8px;
                                    padding:8px 12px; margin-bottom:6px; font-size:0.85rem;">
                            <b style="color:#e2e8f0;">{t.get('task','')}</b><br>
                            <span style="color:#64748b;">👤 {t.get('owner','?')} · 📅 {t.get('deadline','Non définie')}</span>
                        </div>""", unsafe_allow_html=True)

                # Transcription complète
                st.markdown('<div class="card-title" style="margin-top:1rem;">📝 Transcription complète</div>',
                            unsafe_allow_html=True)
                if transcript:
                    html = ""
                    for e in transcript:
                        flag = {"fr":"🇫🇷","en":"🇬🇧","de":"🇩🇪","es":"🇪🇸"}.get(e.get("language","fr"),"🌐")
                        html += f"""
                        <div class="transcript-line">
                            <span class="pill">{e['username']}</span>
                            <span style="font-size:0.7rem;color:#475569;">{e['timestamp']} {flag}</span><br/>
                            <span>{e['text']}</span>
                        </div>"""
                    st.markdown(f'<div class="transcript-box" style="max-height:280px">{html}</div>',
                                unsafe_allow_html=True)

                    # Export
                    export_text = "\n".join(
                        f"[{e['timestamp']}] {e['username']}: {e['text']}" for e in transcript
                    )
                    st.download_button("⬇️ Exporter transcription", export_text,
                                       f"{meeting['name']}_transcript.txt", "text/plain",
                                       use_container_width=True)

                if st.button("🔄 Régénérer", use_container_width=True):
                    from database import get_conn
                    conn = get_conn()
                    conn.execute("DELETE FROM summaries WHERE meeting_id = ?", (selected_id,))
                    conn.commit(); conn.close()
                    st.rerun()

        # ────────────────────────────────────────────────────
        # TAB 2 : CHATBOT
        # ────────────────────────────────────────────────────
        with tab_chat:
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []

            # Contexte pour le chatbot
            meeting_context = f"""Réunion : {meeting['name']}
Durée : {_fmt(duration_sec)}
Participants : {', '.join(p['username'] for p in participants)}
Transcription :
{chr(10).join(f"[{e['timestamp']}] {e['username']}: {e['text']}" for e in transcript)}
"""
            if summary_row:
                meeting_context += f"\nRésumé : {summary_row['summary_text']}"

            st.markdown('<div class="card-title">💬 Discute de ta réunion avec l\'IA</div>',
                        unsafe_allow_html=True)

            # Affichage historique
            for msg in st.session_state.chat_history:
                css_class = "chat-msg-user" if msg["role"] == "user" else "chat-msg-ai"
                prefix = "🧑 Toi" if msg["role"] == "user" else "🤖 Claude"
                st.markdown(f"""
                <div class="{css_class}">
                    <div style="font-size:0.7rem; color:#64748b; margin-bottom:4px;">{prefix}</div>
                    {msg['content']}
                </div>""", unsafe_allow_html=True)

            # Input
            user_msg = st.text_input("", placeholder="Ex: Quelles sont les décisions prises ? Qui a le plus parlé ?",
                                     label_visibility="collapsed", key="chat_input")
            c_send, c_clear = st.columns(2)
            with c_send:
                if st.button("Envoyer ➤", use_container_width=True, key="btn_send_chat"):
                    if user_msg.strip():
                        st.session_state.chat_history.append({"role":"user","content":user_msg})
                        with st.spinner("Claude réfléchit…"):
                            reply = chatbot_response(
                                st.session_state.chat_history[:-1],
                                user_msg, meeting_context
                            )
                        st.session_state.chat_history.append({"role":"assistant","content":reply})
                        st.rerun()
            with c_clear:
                if st.button("🗑 Effacer", use_container_width=True, key="btn_clear_chat"):
                    st.session_state.chat_history = []
                    st.rerun()

        # ────────────────────────────────────────────────────
        # TAB 3 : STATISTIQUES
        # ────────────────────────────────────────────────────
        with tab_stats:

            distraction_events = get_distraction_events(selected_id)
            speech_times       = get_speech_times(selected_id)

            if is_creator:
                # ── VUE CRÉATEUR ──────────────────────────────
                st.markdown('<div class="card-title">👑 Vue Créateur — Statistiques complètes</div>',
                            unsafe_allow_html=True)

                sc1, sc2 = st.columns(2)

                # Temps de parole — donut
                with sc1:
                    st.markdown('<div class="card-title">⏱ Temps de parole</div>', unsafe_allow_html=True)
                    if speech_times and any(v > 0 for v in speech_times.values()):
                        labels = list(speech_times.keys())
                        values = list(speech_times.values())
                        fig = go.Figure(data=[go.Pie(
                            labels=labels, values=values, hole=0.55,
                            marker=dict(colors=COLORS[:len(labels)],
                                        line=dict(color="#08090f", width=2)),
                            textfont=dict(color="white", size=11),
                        )])
                        fig.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#e2e8f0"), margin=dict(t=10,b=10,l=10,r=10),
                            height=220, showlegend=True,
                            legend=dict(font=dict(color="#94a3b8",size=10), bgcolor="rgba(0,0,0,0)")
                        )
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
                    else:
                        st.markdown('<div style="color:#475569; font-size:0.85rem;">Aucune donnée de parole.</div>',
                                    unsafe_allow_html=True)

                # Concentration globale — bar chart
                with sc2:
                    st.markdown('<div class="card-title">🧠 Niveau de concentration — Vue globale</div>',
                                unsafe_allow_html=True)

                    # Calcul concentration moyenne par participant depuis les events
                    conc_by_user = {}
                    for p in participants:
                        p_events = [e for e in distraction_events if e["user_id"] == p.get("id", -1)]
                        if p_events:
                            # Durée totale de distraction
                            total_distract = sum(e["duration_seconds"] for e in p_events)
                            conc_score = max(0, 100 - int(total_distract / duration_sec * 100))
                        else:
                            conc_score = 95  # pas d'events = concentré
                        conc_by_user[p["username"]] = conc_score

                    if conc_by_user:
                        fig2 = go.Figure(data=[go.Bar(
                            x=list(conc_by_user.keys()),
                            y=list(conc_by_user.values()),
                            marker=dict(
                                color=[_score_color(v) for v in conc_by_user.values()],
                                line=dict(color="#08090f", width=1)
                            ),
                            text=[f"{v}%" for v in conc_by_user.values()],
                            textposition="outside",
                            textfont=dict(color="#e2e8f0", size=11),
                        )])
                        fig2.update_layout(
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            font=dict(color="#e2e8f0"), margin=dict(t=20,b=10,l=10,r=10),
                            height=220, yaxis=dict(range=[0,110], showgrid=False, color="#64748b"),
                            xaxis=dict(showgrid=False, color="#94a3b8"),
                        )
                        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar":False})

                # Détail distractions par participant
                st.markdown('<div class="card-title" style="margin-top:0.5rem;">⚠️ Détail des distractions par participant</div>',
                            unsafe_allow_html=True)

                for p in participants:
                    p_events = [e for e in distraction_events if e["user_id"] == p.get("id", -1)]
                    with st.expander(f"👤 {p['username']} — {len(p_events)} événement(s)"):
                        if not p_events:
                            st.markdown('<div style="color:#22d3a0; font-size:0.85rem;">✅ Aucune distraction détectée</div>',
                                        unsafe_allow_html=True)
                        else:
                            for ev in p_events:
                                ts = ev["timestamp"].split("T")[-1][:8] if "T" in ev["timestamp"] else ev["timestamp"]
                                st.markdown(f"""
                                <div style="font-size:0.8rem; padding:4px 0; border-bottom:1px solid #1e2540; color:#cbd5e1;">
                                    🕐 <b>{ts}</b> — {ev['detail']}
                                    <span style="color:#64748b;"> ({ev['duration_seconds']:.0f}s)</span>
                                </div>""", unsafe_allow_html=True)

            else:
                # ── VUE PARTICIPANT ───────────────────────────
                st.markdown('<div class="card-title">👤 Mes statistiques personnelles</div>',
                            unsafe_allow_html=True)

                my_events = [e for e in distraction_events if e["user_id"] == user["id"]]
                total_distract = sum(e["duration_seconds"] for e in my_events)
                my_conc = max(0, 100 - int(total_distract / max(duration_sec, 1) * 100))

                m1, m2 = st.columns(2)
                with m1:
                    col = _score_color(my_conc)
                    st.markdown(f"""
                    <div class="card" style="text-align:center;">
                        <div style="font-family:'Syne',sans-serif; font-size:2.5rem; font-weight:800; color:{col};">{my_conc}%</div>
                        <div style="font-size:0.8rem; color:#64748b;">Mon score de concentration</div>
                    </div>""", unsafe_allow_html=True)
                with m2:
                    st.markdown(f"""
                    <div class="card" style="text-align:center;">
                        <div style="font-family:'Syne',sans-serif; font-size:2.5rem; font-weight:800; color:#f59e0b;">{len(my_events)}</div>
                        <div style="font-size:0.8rem; color:#64748b;">Distractions détectées</div>
                    </div>""", unsafe_allow_html=True)

                # Détail mes distractions
                st.markdown('<div class="card-title" style="margin-top:0.5rem;">⚠️ Mes distractions en détail</div>',
                            unsafe_allow_html=True)
                if not my_events:
                    st.markdown('<div class="ok-box">✅ Aucune distraction détectée — bravo !</div>',
                                unsafe_allow_html=True)
                else:
                    for ev in my_events:
                        ts = ev["timestamp"].split("T")[-1][:8] if "T" in ev["timestamp"] else ev["timestamp"]
                        st.markdown(f"""
                        <div style="font-size:0.82rem; padding:6px 0; border-bottom:1px solid #1e2540; color:#cbd5e1;">
                            🕐 <b>{ts}</b> — {ev['detail']}
                            <span style="color:#64748b;"> ({ev['duration_seconds']:.0f}s)</span>
                        </div>""", unsafe_allow_html=True)

                # Mes thèmes
                st.markdown('<div class="card-title" style="margin-top:1rem;">🏷️ Mes thèmes abordés</div>',
                            unsafe_allow_html=True)
                my_transcript = [e for e in transcript if e.get("username") == user["username"]]
                if my_transcript:
                    if st.button("🔍 Analyser mes thèmes", use_container_width=True):
                        with st.spinner("Analyse en cours…"):
                            themes = get_participant_themes(transcript, user["username"])
                            st.session_state[f"my_themes_{selected_id}"] = themes
                            st.rerun()

                    themes = st.session_state.get(f"my_themes_{selected_id}", [])
                    if themes:
                        pills = " ".join(f'<span class="pill">{t}</span>' for t in themes)
                        st.markdown(f"<div style='margin-top:6px'>{pills}</div>", unsafe_allow_html=True)
                else:
                    st.markdown('<div style="color:#475569; font-size:0.85rem;">Aucune transcription disponible.</div>',
                                unsafe_allow_html=True)