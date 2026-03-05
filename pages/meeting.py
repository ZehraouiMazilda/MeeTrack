import streamlit as st
import time
import threading
import numpy as np
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import av
import cv2

from database import (
    add_transcript, add_distraction_event,
    leave_meeting, end_meeting, get_meeting_participants
)

# ── MediaPipe ─────────────────────────────────────────────────
try:
    import mediapipe as mp
    _fm = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    MP_OK = True
except Exception:
    MP_OK = False
    _fm = None

RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
LEFT_EYE  = [33,  160, 158, 133, 153, 144]
RIGHT_EYE = [263, 387, 385, 362, 380, 373]

class _State:
    def __init__(self):
        self.lock          = threading.Lock()
        self.concentration = 100
        self.face_detected = True
        self.no_face_since = None
        self.alert         = ""
        self._log_event    = None

_shared = _State()


class FaceProcessor(VideoProcessorBase):
    def __init__(self):
        self.fm = _fm

    @staticmethod
    def _ear(pts):
        A = np.linalg.norm(pts[1] - pts[5])
        B = np.linalg.norm(pts[2] - pts[4])
        C = np.linalg.norm(pts[0] - pts[3])
        return (A + B) / (2.0 * C + 1e-6)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        if self.fm is None:
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        h, w = img.shape[:2]
        rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        res  = self.fm.process(rgb)

        if res.multi_face_landmarks:
            lms = res.multi_face_landmarks[0].landmark
            def pts(idx):
                return np.array([[lms[i].x * w, lms[i].y * h] for i in idx])
            ear   = (self._ear(pts(LEFT_EYE)) + self._ear(pts(RIGHT_EYE))) / 2.0
            score = int(np.clip((ear - 0.15) / (0.35 - 0.15) * 100, 0, 100))
            for i in LEFT_EYE + RIGHT_EYE:
                cv2.circle(img, (int(lms[i].x * w), int(lms[i].y * h)), 2, (79, 110, 247), -1)
            color = (34,211,160) if score>60 else (245,158,11) if score>30 else (239,68,68)
            cv2.rectangle(img, (0, 0), (w, 48), (8, 9, 15), -1)
            cv2.putText(img, f"Concentration: {score}%", (12, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
            with _shared.lock:
                _shared.concentration = score
                _shared.face_detected = True
                _shared.no_face_since = None
                if score < 30:
                    _shared.alert = "😴 Fatigue détectée — ouvre les yeux !"
                    _shared._log_event = {"type":"cam_distracted","detail":_shared.alert,"duration":0}
                elif score < 60:
                    _shared.alert = "⚠️ Tu sembles distrait"
                    _shared._log_event = {"type":"cam_distracted","detail":_shared.alert,"duration":0}
                else:
                    _shared.alert = ""
                    _shared._log_event = None
        else:
            now = time.time()
            with _shared.lock:
                if _shared.no_face_since is None:
                    _shared.no_face_since = now
                elapsed_no_face = now - _shared.no_face_since
                _shared.concentration = 0
                _shared.face_detected = False
                if elapsed_no_face > 4:
                    _shared.alert = f"👤 Visage absent depuis {int(elapsed_no_face)}s"
                    _shared._log_event = {"type":"cam_no_face","detail":_shared.alert,"duration":elapsed_no_face}
                else:
                    _shared.alert = ""
                    _shared._log_event = None
            cv2.rectangle(img, (0, 0), (w, 48), (8, 9, 15), -1)
            cv2.putText(img, "Aucun visage détecté", (12, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (239, 68, 68), 2, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


def _score_color(s):
    if s > 60: return "#22d3a0"
    if s > 30: return "#f59e0b"
    return "#ef4444"

def _fmt(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _save_and_exit(meeting, user, is_creator):
    for line in st.session_state.get("manual_transcript", []):
        add_transcript(meeting["id"], user["id"], line["text"], line.get("lang", "fr"))
    for ev in st.session_state.get("distraction_log", []):
        add_distraction_event(meeting["id"], user["id"], ev["type"], ev["detail"], ev.get("duration", 0))
    leave_meeting(meeting["id"], user["id"])
    if is_creator:
        end_meeting(meeting["id"])
    st.session_state.selected_meeting_id = meeting["id"]
    st.session_state.page = "history"
    for k in ["meet_start", "last_alert_time", "manual_transcript", "tab_alert", "conc_history", "distraction_log"]:
        st.session_state.pop(k, None)


def show():
    user       = st.session_state.user
    meeting    = st.session_state.meeting
    is_creator = st.session_state.get("is_creator", False)

    if "meet_start"        not in st.session_state: st.session_state.meet_start        = time.time()
    if "manual_transcript" not in st.session_state: st.session_state.manual_transcript = []
    if "distraction_log"   not in st.session_state: st.session_state.distraction_log   = []
    if "conc_history"      not in st.session_state: st.session_state.conc_history      = []
    if "last_alert_time"   not in st.session_state: st.session_state.last_alert_time   = 0

    elapsed = time.time() - st.session_state.meet_start

    # ── JS : alertes visuelles onglet + curseur ────────────────
    st.markdown("""
    <script>
    (function(){
        document.addEventListener('visibilitychange', function(){
            const w = document.getElementById('tab-warning');
            if(w) w.style.display = document.hidden ? 'block' : 'none';
        });
        let lastMove = Date.now();
        document.addEventListener('mousemove', () => {
            lastMove = Date.now();
            const w = document.getElementById('cursor-warning');
            if(w) w.style.display = 'none';
        });
        setInterval(() => {
            if(Date.now() - lastMove > 30000){
                const w = document.getElementById('cursor-warning');
                if(w) w.style.display = 'block';
            }
        }, 5000);
    })();
    </script>
    <div id="tab-warning" style="display:none;position:fixed;top:16px;left:50%;
        transform:translateX(-50%);z-index:9999;background:rgba(239,68,68,0.95);
        border-radius:12px;padding:14px 28px;color:white;font-family:'Syne',sans-serif;
        font-weight:700;font-size:0.95rem;box-shadow:0 8px 32px rgba(239,68,68,0.4);">
        🚨 Tu as quitté l'onglet — reviens !
    </div>
    <div id="cursor-warning" style="display:none;position:fixed;bottom:24px;right:24px;
        z-index:9999;background:rgba(245,158,11,0.15);border:1px solid #f59e0b;
        border-radius:10px;padding:12px 18px;color:#fcd34d;
        font-family:'Syne',sans-serif;font-size:0.82rem;">
        🖱️ Inactivité détectée — tu es toujours là ?
    </div>
    """, unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────
    h1, h2, h3 = st.columns([2, 3, 2])
    with h1:
        st.markdown(f"""
        <div style="padding-top:6px;">
            <span class="dot-live"></span>
            <span style="font-family:'Syne',sans-serif;font-weight:700;font-size:1rem;">{meeting['name']}</span>
            <br><span style="font-size:0.72rem;color:#64748b;">
                {'👑 Créateur' if is_creator else '👤 Participant'} · {user['username']}
            </span>
        </div>""", unsafe_allow_html=True)
    with h2:
        st.markdown(f"""
        <div style="text-align:center;padding-top:4px;">
            <span style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;color:#e2e8f0;">
                {_fmt(elapsed)}
            </span><br>
            <span style="font-size:0.72rem;color:#64748b;">
                Code : <b style="color:#4f6ef7;letter-spacing:0.1em;">{meeting['code']}</b>
                — Partage ce code pour inviter
            </span>
        </div>""", unsafe_allow_html=True)
    with h3:
        if st.button("⏹ Terminer & résumé" if is_creator else "🚪 Quitter", use_container_width=True):
            _save_and_exit(meeting, user, is_creator)
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Layout : cam gauche | centre contenu ───────────────────
    cam_col, main_col = st.columns([1.2, 2.8])

    # ── GAUCHE : webcam MediaPipe + alertes ────────────────────
    with cam_col:
        st.markdown("""
        <div class="card-title">📷 Ta caméra</div>
        <div style="font-size:0.72rem;color:#64748b;margin-bottom:8px;">
            Analyse IA — visible que par toi
        </div>""", unsafe_allow_html=True)

        ctx = webrtc_streamer(
            key="distraction-cam",
            video_processor_factory=FaceProcessor,
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )

        # Lecture score
        with _shared.lock:
            score  = _shared.concentration
            alert  = _shared.alert
            log_ev = _shared._log_event

        # Log anti-spam 5s
        now = time.time()
        if log_ev and (now - st.session_state.last_alert_time) > 5:
            st.session_state.distraction_log.append(log_ev)
            st.session_state.conc_history.append(score)
            st.session_state.last_alert_time = now

        # Alerte distraction uniquement (pas de métriques — elles sont dans l'historique)
        st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
        if alert:
            st.markdown(f"""
            <div class="alert-box">
                🚨 {alert}<br>
                <span style="font-size:0.72rem;opacity:0.7;">Visible uniquement par toi</span>
            </div>""", unsafe_allow_html=True)
        else:
            if ctx and ctx.state.playing:
                st.markdown('<div class="ok-box">✅ Tu es concentré</div>', unsafe_allow_html=True)

        # Participants
        st.markdown('<div class="card-title" style="margin-top:1.2rem;">👥 Participants</div>',
                    unsafe_allow_html=True)
        for p in get_meeting_participants(meeting["id"]):
            is_me = p["username"] == user["username"]
            dot   = "🟢" if p["left_at"] is None else "⚫"
            me    = " <span style='color:#4f6ef7;font-size:0.7rem;'>(toi)</span>" if is_me else ""
            st.markdown(f"""
            <div style="font-size:0.82rem;padding:6px 0;
                        border-bottom:1px solid #1e2540;color:#cbd5e1;">
                {dot} <b>{p['username']}</b>{me}
            </div>""", unsafe_allow_html=True)

    # ── DROITE : Audio Jitsi (8x8.vc) + transcription ─────────
    with main_col:

        # Audio Jitsi via 8x8.vc — illimité, gratuit, sans compte
        st.markdown('<div class="card-title">🎧 Audio en direct</div>', unsafe_allow_html=True)

        room_name = f"meetrack-{meeting['code']}"
        username  = user['username']

        # 8x8.vc = Jitsi illimité sans compte
        jitsi_src = (
            f"https://meet.jit.si/{room_name}"
            f"#config.prejoinPageEnabled=false"
            f"&config.startWithVideoMuted=true"
            f"&config.startWithAudioMuted=false"
            f"&config.disableDeepLinking=true"
            f"&userInfo.displayName=\"{username}\""
        )

        st.markdown(f"""
        <div style="border-radius:14px;overflow:hidden;border:1px solid #1e2540;">
        <iframe
            src="{jitsi_src}"
            width="100%" height="380"
            allow="microphone; fullscreen"
            style="border:none;display:block;background:#08090f;"
        ></iframe>
        </div>""", unsafe_allow_html=True)

        # ── Transcription ──────────────────────────────────────
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">📝 Transcription</div>', unsafe_allow_html=True)

        t1, t2, t3 = st.columns([3, 1, 1])
        with t1:
            txt = st.text_input("", placeholder="Tape ce qui est dit...",
                                label_visibility="collapsed", key="t_input")
        with t2:
            lang = st.selectbox("", ["🇫🇷 FR","🇬🇧 EN","🇩🇪 DE","🇪🇸 ES"],
                                label_visibility="collapsed", key="lang_sel")
            lang_code = lang.split(" ")[1].lower()
        with t3:
            if st.button("➕ Ajouter", use_container_width=True):
                if txt.strip():
                    st.session_state.manual_transcript.append({
                        "text": txt.strip(),
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "user": user["username"],
                        "lang": lang_code
                    })
                    st.rerun()

        if st.session_state.manual_transcript:
            lines_html = ""
            for entry in st.session_state.manual_transcript[-8:]:
                flag = {"fr":"🇫🇷","en":"🇬🇧","de":"🇩🇪","es":"🇪🇸"}.get(entry.get("lang","fr"),"🌐")
                lines_html += f"""
                <div class="transcript-line">
                    <span class="pill">{entry['user']}</span>
                    <span style="font-size:0.7rem;color:#475569;">{entry['time']} {flag}</span><br/>
                    <span>{entry['text']}</span>
                </div>"""
            st.markdown(f'<div class="transcript-box">{lines_html}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="transcript-box" style="color:#475569;font-size:0.85rem;">'
                'En attente de transcription…</div>',
                unsafe_allow_html=True)

        # Compteur discret
        nb = len(st.session_state.manual_transcript)
        nd = len(st.session_state.distraction_log)
        if nb > 0 or nd > 0:
            st.markdown(f"""
            <div style="margin-top:0.6rem;font-size:0.75rem;color:#475569;text-align:right;">
                📝 {nb} ligne(s) · ⚠️ {nd} alerte(s) enregistrée(s)
            </div>""", unsafe_allow_html=True)