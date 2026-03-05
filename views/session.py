import streamlit as st
import time
import av
import io
import os
import base64
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

from database import (
    init_db, create_session, update_session,
    add_source, get_sources, delete_source,
    add_note, get_notes, delete_note,
    add_chat_message, get_chat_messages,
    add_transcript, add_distraction,
    add_timeline_point, init_session_stats,
    increment_alert_stat, finalize_session_stats,
)
from services.vision import process_frame, shared_state, start_calibration
from services.concentration_engine import engine
from services.cursor_tracker import inject_cursor_tracker
from services.voice_detector import (
    start_listening, stop_listening,
    set_session_theme, set_callbacks,
    get_status as vd_status, play_tts,
)

init_db()
RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

class VisionProcessor(VideoProcessorBase):
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = process_frame(img)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

def _fmt_time(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def _score_color(s):
    if s >= 70: return "#22c55e"
    if s >= 45: return "#f97316"
    return "#ef4444"

def _extract_pdf(raw: bytes) -> str:
    try:
        import PyPDF2
        r = PyPDF2.PdfReader(io.BytesIO(raw))
        return "\n".join(p.extract_text() or "" for p in r.pages)
    except: return ""

def _get_groq():
    import httpx
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv()
    return Groq(api_key=os.getenv("GROQ_API_KEY"), http_client=httpx.Client(verify=True))

def _groq_clean_note(raw: str) -> str:
    try:
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":f"Corrige l'orthographe UNIQUEMENT. Réponds avec la note corrigée seulement.\n\n{raw}"}],
            max_tokens=300, temperature=0.1)
        return r.choices[0].message.content.strip()
    except: return raw

def _groq_chat(history: list, src_content: str, title: str) -> str:
    try:
        has_src = bool(src_content and src_content.strip())
        system = (
            f'Tu es Lumi, assistant d\'étude pour la session "{title}".\n'
            + ("Sources:\n" + src_content[:4000] if has_src else "Aucune source.")
            + "\nRéponds en 3-5 phrases complètes. Ne coupe JAMAIS une phrase en plein milieu. Termine toujours sur une phrase complète. Français."
        )
        msgs = [{"role":"system","content":system}] + [
            {"role":m["role"],"content":m["content"]} for m in history[-10:]
        ]
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant", messages=msgs, max_tokens=500, temperature=0.7)
        return r.choices[0].message.content.strip()
    except Exception as e: return f"Erreur: {e}"

def _groq_summary(src_content: str, title: str) -> str:
    try:
        has_src = bool(src_content and src_content.strip())
        prompt = (
            f"Session: '{title}'\n"
            + ("Sources: " + src_content[:2000] if has_src else "Pas de sources.")
            + "\nRésumé ultra-court en 2 phrases. Si pas de sources, dis bonjour."
        )
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":prompt}],
            max_tokens=150, temperature=0.5)
        return r.choices[0].message.content.strip()
    except: return "Bonjour ! Je suis Lumi. Upload tes cours pour commencer !"

def _setup_voice(sid: int, title: str, src_content: str):
    set_session_theme(title)
    def on_question(text: str):
        try:
            h = get_chat_messages(sid)
            h.append({"role":"user","content":text})
            reply = _groq_chat(h, src_content, title)
            add_chat_message(sid, "user", text)
            add_chat_message(sid, "assistant", reply)
            add_transcript(sid, text, mode="lumi")
            increment_alert_stat(sid, "lumi_call")
            print(f"[CHAT SAVED] Q: {text[:40]} | A: {reply[:40]}", flush=True)
            play_tts(reply)
        except Exception as e:
            print(f"[on_question error] {e}", flush=True)
    def on_alert(msg: str):
        pass  # popup géré via DB
    set_callbacks(on_lumi_question=on_question, on_alert=on_alert)
    start_listening()

def show():
    inject_cursor_tracker()

    st.markdown("""
    <style>
    .block-container { padding: 0.6rem 1.2rem !important; max-width: 100% !important; }
    .score-card { background:#2d2040; border:1.5px solid #4a3560; border-radius:14px; padding:0.9rem; text-align:center; }
    .score-lbl { font-size:0.62rem; color:#a896c8; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; }
    .chat-wrap { max-height:400px; overflow-y:auto; padding-right:4px; margin-bottom:8px; }
    .chat-user { background:linear-gradient(135deg,#9b6dff,#7c4fe0); color:white; border-radius:18px 18px 4px 18px; padding:9px 14px; margin:4px 0 4px 12%; font-size:0.9rem; }
    .chat-lumi { background:#2d2040; border:1.5px solid #4a3560; border-radius:18px 18px 18px 4px; padding:9px 14px; margin:4px 12% 4px 0; font-size:0.9rem; color:#f0eaff; }
    .chat-lbl { font-size:0.6rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; opacity:0.5; margin-bottom:2px; }
    .note-item { background:#2d2040; border:1px solid #4a3560; border-radius:10px; padding:9px 13px; margin-bottom:6px; font-size:0.88rem; color:#f0eaff; }
    .pdf-thumb { background:#2d2040; border:1.5px solid #4a3560; border-radius:12px; padding:1rem; text-align:center; cursor:pointer; transition:border-color 0.2s; }
    .pdf-thumb:hover { border-color:#9b6dff; }
    .gate-box { background:#2d2040; border:2px dashed #4a3560; border-radius:20px; padding:3rem 2rem; text-align:center; margin:1rem 0; }
    .src-item { font-size:0.82rem; color:#f0eaff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-top:5px; }
    </style>
    """, unsafe_allow_html=True)

    # Init session
    if not st.session_state.get("session_id"):
        title = st.session_state.get("new_session_title", "Nouvelle session")
        sid   = create_session(title)
        init_session_stats(sid)
        st.session_state.update({
            "session_id": sid, "session_title": title,
            "session_start": time.time(), "summary_done": False,
            "open_source": None, "voice_started": False,
            "_last_msg_count": 0,
            "_last_snapshot": time.time(),
            "_lumi_calls": 0,
        })

    sid     = st.session_state["session_id"]
    title   = st.session_state["session_title"]
    elapsed = time.time() - st.session_state["session_start"]
    sources = get_sources(sid)
    has_src = len(sources) > 0
    src_content = "\n\n".join(s.get("content","") for s in sources if s.get("content"))

    if has_src and not st.session_state.get("voice_started"):
        _setup_voice(sid, title, src_content)
        st.session_state["voice_started"] = True

    # ── HEADER ──────────────────────────────────────────────
    h1, h2, h3 = st.columns([1, 3, 1])
    with h1:
        st.markdown("<div style='font-size:1.4rem;font-weight:800;color:#9b6dff;padding-top:4px;'>🌟 Lumi</div>", unsafe_allow_html=True)
    with h2:
        st.markdown(f'<div style="text-align:center;line-height:1.3;"><div style="font-size:1rem;font-weight:700;color:#f0eaff;">{title}</div><div style="font-size:1.7rem;font-weight:800;color:#9b6dff;">{_fmt_time(elapsed)}</div></div>', unsafe_allow_html=True)
    with h3:
        if st.button("🚪 Quitter", use_container_width=True, key="quit_btn"):
            # Résumé auto pour les stats
            summary = _groq_summary(src_content, title) if src_content else ""
            update_session(sid, duration_sec=elapsed)
            finalize_session_stats(sid, summary=summary)
            stop_listening()
            for k in ["session_id","session_title","session_start","summary_done",
                      "open_source","voice_started","new_session_title","_last_msg_count",
                      "_last_snapshot","_lumi_calls"]:
                st.session_state.pop(k, None)
            st.session_state["page"] = "home"
            st.rerun()

    st.markdown("<hr style='margin:0.4rem 0 0.8rem;border-color:#2d2040;'>", unsafe_allow_html=True)

    # ── LAYOUT ──────────────────────────────────────────────
    sidebar, main = st.columns([1, 3], gap="medium")

    with sidebar:
        st.markdown("<div style='font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#9b6dff;margin-bottom:0.5rem;'>📄 Sources</div>", unsafe_allow_html=True)
        to_delete = []
        for s in sources:
            c1, c2 = st.columns([1, 6])
            with c1:
                if st.checkbox("", key=f"chk_{s['id']}", label_visibility="collapsed"):
                    to_delete.append(s["id"])
            with c2:
                st.markdown(f"<div class='src-item'>📄 {s['filename']}</div>", unsafe_allow_html=True)
        if not sources:
            st.markdown("<div style='font-size:0.8rem;color:#7a6a9a;'>Aucune source</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        uploaded = st.file_uploader("", type=["pdf","txt"], label_visibility="collapsed", key="uploader")
        if uploaded is not None:
            existing = [s["filename"] for s in get_sources(sid)]
            if uploaded.name not in existing:
                raw = uploaded.read()
                content = _extract_pdf(raw) if uploaded.type=="application/pdf" else raw.decode("utf-8",errors="ignore")
                if uploaded.type == "application/pdf":
                    st.session_state[f"pdf_{uploaded.name}"] = raw
                add_source(sid, uploaded.name, content)
                st.rerun()
        if to_delete:
            if st.button("🗑 Supprimer", use_container_width=True, key="del_src"):
                for did in to_delete:
                    delete_source(did)
                st.session_state["open_source"] = None
                st.rerun()

    with main:
        if not has_src:
            st.markdown('<div class="gate-box"><div style="font-size:3rem;">📂</div><div style="font-size:1.2rem;font-weight:700;color:#f0eaff;margin:0.5rem 0;">Upload tes sources pour commencer</div><div style="font-size:0.88rem;color:#7a6a9a;">Lumi, la caméra et le micro s\'activent une fois tes cours chargés.</div></div>', unsafe_allow_html=True)
            time.sleep(2); st.rerun(); return

        cam_col, score_col = st.columns([3, 2], gap="medium")
        with cam_col:
            webrtc_streamer(key="lumi-cam", video_processor_factory=VisionProcessor,
                rtc_configuration=RTC_CONFIG,
                media_stream_constraints={"video":{"facingMode":"user"},"audio":False},
                async_processing=True)
            with shared_state.lock:
                calibrated = shared_state.calibrated
            if not calibrated:
                if st.button("🎯 Calibrer (3s)", use_container_width=True, key="calib"):
                    start_calibration(); st.rerun()

        with score_col:
            with shared_state.lock:
                cam_score = shared_state.score
                cam_alert = shared_state.alert
                ear       = shared_state.ear
            engine.update_cursor(st.session_state.get("cursor_idle",0))
            engine.update_tab(st.session_state.get("tab_visible",True))
            final = engine.compute_final(cam_score)
            fc = _score_color(final); cc = _score_color(cam_score)
            st.markdown(f'<div class="score-card" style="margin-bottom:8px;"><div class="score-lbl">Score Global</div><div style="font-size:2.4rem;font-weight:800;color:{fc};">{final}%</div><div style="background:#382850;border-radius:99px;height:7px;margin-top:6px;overflow:hidden;"><div style="width:{final}%;height:100%;background:{fc};border-radius:99px;"></div></div></div>', unsafe_allow_html=True)
            ec = "#22c55e" if ear > 0.25 else "#f97316"
            st.markdown(f'<div style="display:flex;gap:6px;margin-bottom:6px;"><div class="score-card" style="flex:1;"><div class="score-lbl">📷 Caméra</div><div style="font-size:1.4rem;font-weight:800;color:{cc};">{cam_score}%</div></div><div class="score-card" style="flex:1;"><div class="score-lbl">👁 EAR</div><div style="font-size:1.4rem;font-weight:800;color:{ec};">{ear:.2f}</div></div></div>', unsafe_allow_html=True)
            vs = vd_status()
            lumi_on = vs.get("lumi_mode", False)
            st.markdown(f'<div style="background:{"#3d1f4a" if lumi_on else "#2d2040"};border:1.5px solid {"#9b6dff" if lumi_on else "#4a3560"};border-radius:10px;padding:7px 12px;font-size:0.8rem;color:#f0eaff;margin-top:8px;">{"🎤 Mode Lumi actif — dis <b>merci Lumi</b> pour terminer" if lumi_on else "💡 Dis <b style=color:#9b6dff>Lumi</b> pour me parler"}</div>', unsafe_allow_html=True)
            if cam_alert:
                # Alerte auto-disparition via JS
                st.markdown(f"""
                <div id="cam-alert" style="background:#3d0f0f;border:1.5px solid #ef4444;
                     border-radius:10px;padding:8px 14px;font-size:0.82rem;color:#fca5a5;
                     margin-top:8px;">
                    {cam_alert}
                </div>
                <script>
                setTimeout(function(){{
                    var el = document.getElementById('cam-alert');
                    if(el) el.style.display='none';
                }}, 5000);
                </script>""", unsafe_allow_html=True)

    # ── DEBUG ────────────────────────────────────────────────
    vs = vd_status()
    lumi_on = vs.get("lumi_mode", False)
    with st.expander("🔬 Debug voix", expanded=False):
        d1,d2,d3,d4 = st.columns(4)
        d1.metric("Loop",  "🟢 ON"  if vs.get("running")      else "🔴 OFF")
        d2.metric("Enreg.","🔴 OUI" if vs.get("is_recording") else "⚪ non")
        d3.metric("Lumi",  "🟣 OUI" if lumi_on               else "⚪ non")
        d4.metric("Parle", "🔊 OUI" if vs.get("is_speaking")  else "⚪ non")
        if vs.get("last_transcript"):
            st.caption(f"Transcription: {vs['last_transcript']}")

    # ── ONGLETS ──────────────────────────────────────────────
    tab_src, tab_lumi = st.tabs(["📄 Sources", "🌟 Lumi"])

    with tab_src:
        open_src = st.session_state.get("open_source")
        if not open_src:
            ncols = min(len(sources), 3)
            cols  = st.columns(ncols, gap="medium")
            for i, s in enumerate(sources):
                with cols[i % ncols]:
                    st.markdown(f'<div class="pdf-thumb"><div style="font-size:2.2rem;">📄</div><div style="font-size:0.8rem;color:#b89aff;margin-top:4px;font-weight:600;">{s["filename"]}</div></div>', unsafe_allow_html=True)
                    if st.button("Ouvrir", key=f"open_{s['id']}", use_container_width=True):
                        st.session_state["open_source"] = s["id"]; st.rerun()
        else:
            src = next((s for s in sources if s["id"] == open_src), None)
            if not src:
                st.session_state["open_source"] = None; st.rerun(); return
            st.markdown(f"<div style='font-weight:700;color:#b89aff;margin-bottom:8px;'>📄 {src['filename']}</div>", unsafe_allow_html=True)
            pdf_bytes = st.session_state.get(f"pdf_{src['filename']}")
            if pdf_bytes and src["filename"].lower().endswith(".pdf"):
                b64 = base64.b64encode(pdf_bytes).decode()
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=1" width="100%" height="500px" style="border:1.5px solid #4a3560;border-radius:12px;"></iframe>', unsafe_allow_html=True)
            else:
                content = src.get("content","") or "Contenu non disponible."
                st.markdown(f'<div style="background:#221830;border:1px solid #4a3560;border-radius:12px;padding:1rem;max-height:320px;overflow-y:auto;font-size:0.84rem;color:#c4b8e0;line-height:1.7;white-space:pre-wrap;">{content[:5000]}</div>', unsafe_allow_html=True)
            st.markdown("<div style='font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#9b6dff;margin:0.8rem 0 0.4rem;'>📝 Notes</div>", unsafe_allow_html=True)
            for n in get_notes(sid, src["id"]):
                nc1, nc2 = st.columns([6,1])
                with nc1:
                    st.markdown(f'<div class="note-item"><div style="font-size:0.62rem;color:#7a6a9a;">{n["created_at"][:16]}</div>{n["clean_text"]}</div>', unsafe_allow_html=True)
                with nc2:
                    if st.button("🗑", key=f"dn_{n['id']}"): delete_note(n["id"]); st.rerun()
            note_txt = st.text_area("", placeholder="Ta note ici...", label_visibility="collapsed", key=f"ni_{src['id']}", height=70)
            if st.button("✨ Ajouter (Lumi corrige)", key=f"an_{src['id']}", use_container_width=True):
                if note_txt.strip():
                    with st.spinner("Lumi corrige..."):
                        clean = _groq_clean_note(note_txt.strip())
                    add_note(sid, note_txt.strip(), clean, src["id"]); st.rerun()
            if st.button("← Retour", key="back_src"):
                st.session_state["open_source"] = None; st.rerun()

    with tab_lumi:
        if not st.session_state.get("summary_done"):
            with st.spinner("🌟 Lumi prépare un résumé..."):
                summary = _groq_summary(src_content, title)
            add_chat_message(sid, "assistant", summary)
            st.session_state["summary_done"] = True

        # Affiche tous les messages
        chat_msgs = get_chat_messages(sid)
        st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)
        for m in chat_msgs[-30:]:
            if m["role"] == "user":
                st.markdown(f'<div><div class="chat-lbl" style="text-align:right;color:#a896c8;">Toi</div><div class="chat-user">{m["content"]}</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div><div class="chat-lbl" style="color:#9b6dff;">🌟 Lumi</div><div class="chat-lumi">{m["content"]}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        mc, bc = st.columns([4,1])
        with mc:
            user_input = st.text_input("", placeholder="Pose une question par écrit...", label_visibility="collapsed", key="chat_input")
        with bc:
            if st.button("Envoyer →", use_container_width=True, key="send"):
                if user_input.strip():
                    add_chat_message(sid, "user", user_input.strip())
                    h = get_chat_messages(sid)
                    with st.spinner("Lumi réfléchit..."):
                        reply = _groq_chat(h, src_content, title)
                    add_chat_message(sid, "assistant", reply)
                    st.rerun()

    # ── SNAPSHOT concentration toutes les 30s ────────────────
    now = time.time()
    if now - st.session_state.get("_last_snapshot", 0) >= 30:
        st.session_state["_last_snapshot"] = now
        with shared_state.lock:
            snap_score  = shared_state.score
            snap_ear    = shared_state.ear
            snap_yaw    = shared_state.yaw
            snap_pitch  = shared_state.pitch
            snap_alert  = shared_state.alert_type
        vs_snap = vd_status()
        engine_status = engine.get_status()
        add_timeline_point(
            sid, elapsed,
            score_global   = engine.compute_final(snap_score),
            score_camera   = snap_score,
            score_behavior = engine_status.get("behavior_score", 100),
            ear=snap_ear, yaw=snap_yaw, pitch=snap_pitch,
            lumi_mode=vs_snap.get("lumi_mode", False)
        )
        if snap_alert:
            increment_alert_stat(sid, snap_alert)

    # ── POLLING : refresh si nouveaux messages vocaux ────────
    current_count = len(get_chat_messages(sid))
    prev_count    = st.session_state.get("_last_msg_count", 0)
    if current_count != prev_count:
        st.session_state["_last_msg_count"] = current_count
        st.rerun()
    else:
        time.sleep(2)
        st.rerun()