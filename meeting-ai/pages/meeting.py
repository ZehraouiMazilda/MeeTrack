import streamlit as st
import time
import numpy as np
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
import av
import cv2
import threading

# ── Try importing MediaPipe ───────────────────────────────────
MP_AVAILABLE = False
mp_face_mesh = None

try:
    import mediapipe as mp
    try:
        from mediapipe.python.solutions import face_mesh as _face_mesh
        mp_face_mesh = _face_mesh
        MP_AVAILABLE = True
    except Exception:
        MP_AVAILABLE = False
except ImportError:
    MP_AVAILABLE = False

RTC_CONFIG = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

VIDEO_CONSTRAINTS = {
    "video": {
        "width":     {"ideal": 1280, "min": 640},
        "height":    {"ideal": 720,  "min": 480},
        "frameRate": {"ideal": 30,   "min": 15},
        "facingMode": "user",
    },
    "audio": False,
}

class SharedState:
    def __init__(self):
        self.lock          = threading.Lock()
        self.concentration = 85
        self.face_detected = False

_shared = SharedState()


class FaceProcessor(VideoProcessorBase):
    LEFT_EYE  = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [263, 387, 385, 362, 380, 373]

    def __init__(self):
        self.face_mesh    = None
        self._frame_count = 0
        if MP_AVAILABLE and mp_face_mesh is not None:
            try:
                self.face_mesh = mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception:
                self.face_mesh = None

    @staticmethod
    def _ear(pts):
        A = np.linalg.norm(pts[1] - pts[5])
        B = np.linalg.norm(pts[2] - pts[4])
        C = np.linalg.norm(pts[0] - pts[3])
        return (A + B) / (2.0 * C + 1e-6)

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        self._frame_count += 1
        if self._frame_count % 2 != 0:
            return av.VideoFrame.from_ndarray(img, format="bgr24")
        if self.face_mesh is None:
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        h, w, _ = img.shape
        rgb     = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        if results.multi_face_landmarks:
            lms = results.multi_face_landmarks[0].landmark
            for idx in self.LEFT_EYE + self.RIGHT_EYE:
                cv2.circle(img, (int(lms[idx].x * w), int(lms[idx].y * h)), 3, (79, 110, 247), -1)

            def pts(indices):
                return np.array([[lms[i].x * w, lms[i].y * h] for i in indices])

            avg_ear = (self._ear(pts(self.LEFT_EYE)) + self._ear(pts(self.RIGHT_EYE))) / 2.0
            score   = int(np.clip((avg_ear - 0.15) / (0.35 - 0.15) * 100, 0, 100))

            with _shared.lock:
                _shared.concentration = score
                _shared.face_detected = True

            color = (34, 211, 160) if score > 60 else (245, 158, 11) if score > 30 else (239, 68, 68)
            cv2.rectangle(img, (0, 0), (w, 52), (10, 13, 20), -1)
            cv2.putText(img, f"Concentration : {score}%", (14, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
        else:
            with _shared.lock:
                _shared.concentration = 0
                _shared.face_detected = False
            cv2.rectangle(img, (0, 0), (w, 52), (10, 13, 20), -1)
            cv2.putText(img, "Aucun visage", (14, 34),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (239, 68, 68), 2, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


def score_color(s):
    if s > 60: return "#22d3a0"
    if s > 30: return "#f59e0b"
    return "#ef4444"

def score_label(s):
    if s > 60: return "Concentré ✓"
    if s > 30: return "Distrait"
    return "Absent / Endormi"

def fmt(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def show():
    if "start_time"     not in st.session_state: st.session_state.start_time     = time.time()
    if "transcript"     not in st.session_state: st.session_state.transcript     = []
    if "speech_times"   not in st.session_state: st.session_state.speech_times   = {}
    if "conc_history"   not in st.session_state: st.session_state.conc_history   = []
    if "last_tick"      not in st.session_state: st.session_state.last_tick      = time.time()
    if "participants"   not in st.session_state: st.session_state.participants   = ["Alice", "Bob"]
    if "meeting_name"   not in st.session_state: st.session_state.meeting_name  = "Réunion"
    if "active_speaker" not in st.session_state: st.session_state.active_speaker = st.session_state.participants[0]

    participants = st.session_state.participants
    elapsed      = time.time() - st.session_state.start_time

    # ── Top bar ──
    left, mid, right = st.columns([2, 3, 2])
    with left:
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;padding-top:6px;">
            <span class="dot-live"></span>
            <span style="font-family:'Syne',sans-serif;font-weight:700;font-size:1rem;color:#e2e8f0;">
                {st.session_state.meeting_name}
            </span>
        </div>""", unsafe_allow_html=True)
    with mid:
        st.markdown(f"""
        <div style="text-align:center;font-family:'Syne',sans-serif;font-size:1.7rem;
                    font-weight:800;color:#e2e8f0;letter-spacing:0.06em;">{fmt(elapsed)}</div>
        """, unsafe_allow_html=True)
    with right:
        if st.button("⏹ Terminer & résumé", use_container_width=True):
            st.session_state.page = "summary"
            st.rerun()

    st.markdown("<hr style='border-color:#1e2540;margin:0.6rem 0 1rem'>", unsafe_allow_html=True)

    cam_col, metrics_col, sub_col = st.columns([3, 2, 2])

    # ── WEBCAM ──
    with cam_col:
        st.markdown('<div class="card-title">📹 Flux vidéo HD</div>', unsafe_allow_html=True)
        ctx = webrtc_streamer(
            key="meeting-cam",
            video_processor_factory=FaceProcessor,
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints=VIDEO_CONSTRAINTS,
            async_processing=True,

        )

        st.markdown("<div style='margin-top:0.8rem'></div>", unsafe_allow_html=True)
        active = st.selectbox(
            "🎙 Locuteur actif",
            participants,
            index=participants.index(st.session_state.active_speaker)
                  if st.session_state.active_speaker in participants else 0,
        )
        if active != st.session_state.active_speaker:
            st.session_state.active_speaker = active

    # ── METRICS ──
    with metrics_col:
        with _shared.lock:
            score = _shared.concentration

        # Tick every 2s without auto-rerun
        now = time.time()
        if now - st.session_state.last_tick >= 2.0:
            st.session_state.conc_history.append(score)
            if len(st.session_state.conc_history) > 60:
                st.session_state.conc_history.pop(0)
            if ctx and ctx.state.playing:
                st.session_state.speech_times[active] = \
                    st.session_state.speech_times.get(active, 0) + 2.0
            st.session_state.last_tick = now

        avg_score = int(np.mean(st.session_state.conc_history)) if st.session_state.conc_history else score
        col       = score_color(score)

        st.markdown(f"""
        <div class="card">
            <div class="card-title">🧠 Concentration</div>
            <div class="metric-value" style="color:{col};">{score}%</div>
            <div class="metric-label" style="margin-top:4px;">{score_label(score)}</div>
            <div class="prog-bar-bg">
                <div class="prog-bar-fill" style="width:{score}%;background:{col};"></div>
            </div>
            <div style="margin-top:0.6rem;font-size:0.78rem;color:#64748b;">
                Moyenne : <b style="color:{score_color(avg_score)}">{avg_score}%</b>
            </div>
        </div>""", unsafe_allow_html=True)

        st.markdown('<div class="card-title" style="margin-top:0.5rem;">⏱ Temps de parole</div>',
                    unsafe_allow_html=True)

        total_speech = sum(st.session_state.speech_times.values()) or 1
        colors_map   = ["#4f6ef7", "#22d3a0", "#f59e0b", "#ef4444", "#7c3aed", "#ec4899", "#06b6d4"]

        for i, p in enumerate(participants):
            t   = st.session_state.speech_times.get(p, 0)
            pct = int(t / total_speech * 100)
            c   = colors_map[i % len(colors_map)]
            is_active = (p == active and ctx and ctx.state.playing)
            badge = " <span style='font-size:0.65rem;color:#22d3a0;'>● live</span>" if is_active else ""
            st.markdown(f"""
            <div style="margin-bottom:0.8rem;">
                <div style="display:flex;justify-content:space-between;font-size:0.82rem;margin-bottom:4px;">
                    <span style="font-weight:500;color:#e2e8f0;">{p}{badge}</span>
                    <span style="color:#64748b;">{fmt(t)} · {pct}%</span>
                </div>
                <div class="prog-bar-bg">
                    <div class="prog-bar-fill" style="width:{pct}%;background:{c};"></div>
                </div>
            </div>""", unsafe_allow_html=True)

        if st.button("🔄 Actualiser", use_container_width=True):
            st.rerun()

    # ── TRANSCRIPTION ──
    with sub_col:
        st.markdown('<div class="card-title">📝 Transcription live</div>', unsafe_allow_html=True)

        new_line = st.text_input(
            "Transcription",
            placeholder="Ce que vous entendez...",
            label_visibility="collapsed",
            key="manual_input",
        )
        c1, c2 = st.columns(2)
        with c1:
            add_clicked = st.button("➕ Ajouter", use_container_width=True, key="btn_add")
        with c2:
            clear_clicked = st.button("🗑 Effacer", use_container_width=True, key="btn_clear")

        if add_clicked and new_line.strip():
            st.session_state.transcript.append({
                "speaker": st.session_state.active_speaker,
                "text":    new_line.strip(),
                "time":    fmt(elapsed),
            })
            st.rerun()

        if clear_clicked:
            st.session_state.transcript = []
            st.rerun()

        transcript_html = ""
        for entry in st.session_state.transcript[-12:]:
            transcript_html += f"""
            <div class="subtitle-line">
                <span class="speaker-pill">{entry['speaker']}</span>
                <span style="font-size:0.72rem;color:#475569;">{entry['time']}</span><br/>
                <span style="font-size:0.9rem;">{entry['text']}</span>
            </div>"""

        if not transcript_html:
            transcript_html = '<div style="color:#475569;font-size:0.85rem;padding:0.5rem 0;">En attente de transcription…</div>'

        st.markdown(f'<div class="subtitle-box">{transcript_html}</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="card-title">📈 Historique concentration</div>', unsafe_allow_html=True)

        if len(st.session_state.conc_history) > 1:
            import pandas as pd
            st.line_chart(
                pd.DataFrame({"Concentration (%)": st.session_state.conc_history}),
                height=110,
                use_container_width=True,
            )
        else:
            st.markdown('<div style="color:#475569;font-size:0.82rem;">Démarrez la caméra pour voir l\'historique.</div>',
                        unsafe_allow_html=True)
