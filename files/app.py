"""
FocusMeet — Multi-participant concentration monitor
Deploy on Streamlit Community Cloud + Upstash Redis for shared state.

Local fallback: if no Redis URL is set, uses in-memory dict (single machine only).
"""
import streamlit as st
import cv2
import numpy as np
import time
import urllib.request
import json
import os
import threading
from collections import deque
from pathlib import Path
import av
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FocusMeet",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════════
# SHARED STATE BACKEND
# - If REDIS_URL env var is set  → use Redis (works across multiple cloud workers)
# - Otherwise                    → use in-memory dict (single server / local use)
# ═══════════════════════════════════════════════════════════════════════════════
REDIS_URL = os.environ.get("REDIS_URL", "")   # set in Streamlit Cloud secrets

class RedisBackend:
    """Upstash Redis via REST API — no extra package needed, just requests."""
    def __init__(self, url):
        # url format: https://xxx.upstash.io  (from Upstash console)
        # token comes from REDIS_TOKEN env var
        self.url   = url.rstrip("/")
        self.token = os.environ.get("REDIS_TOKEN", "")
        self.ttl   = 3600   # rooms expire after 1 hour of inactivity

    def _req(self, *cmd):
        import urllib.request, json
        payload = json.dumps(list(cmd)).encode()
        req = urllib.request.Request(
            f"{self.url}/pipeline",
            data=json.dumps([list(cmd)]).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())[0]["result"]

    def get_room(self, code):
        raw = self._req("GET", f"room:{code}")
        return json.loads(raw) if raw else None

    def set_room(self, code, data):
        self._req("SET", f"room:{code}", json.dumps(data), "EX", self.ttl)

    def room_exists(self, code):
        return self._req("EXISTS", f"room:{code}") == 1

    def update_score(self, code, pid, score_data):
        room = self.get_room(code) or {"participants":{}, "scores":{}}
        room["scores"][pid] = score_data
        self.set_room(code, room)

    def add_participant(self, code, pid, name):
        room = self.get_room(code) or {"participants":{}, "scores":{}}
        room["participants"][pid] = name
        room["scores"].setdefault(pid, dict(score=0,ear=0,yaw=0,pitch=0,
                                             blink_rate=0,face_found=False))
        self.set_room(code, room)

    def remove_participant(self, code, pid):
        room = self.get_room(code)
        if not room: return
        room["participants"].pop(pid, None)
        room["scores"].pop(pid, None)
        if room["participants"]:
            self.set_room(code, room)
        else:
            self._req("DEL", f"room:{code}")


class MemoryBackend:
    """In-memory fallback for single-server / local use."""
    def __init__(self):
        self._rooms = {}
        self._lock  = threading.Lock()

    def get_room(self, code):
        return self._rooms.get(code)

    def set_room(self, code, data):
        self._rooms[code] = data

    def room_exists(self, code):
        return code in self._rooms

    def update_score(self, code, pid, score_data):
        with self._lock:
            if code in self._rooms:
                self._rooms[code]["scores"][pid] = score_data

    def add_participant(self, code, pid, name):
        with self._lock:
            if code not in self._rooms:
                self._rooms[code] = {"participants":{}, "scores":{}}
            self._rooms[code]["participants"][pid] = name
            self._rooms[code]["scores"].setdefault(
                pid, dict(score=0,ear=0,yaw=0,pitch=0,blink_rate=0,face_found=False))

    def remove_participant(self, code, pid):
        with self._lock:
            if code not in self._rooms: return
            self._rooms[code]["participants"].pop(pid, None)
            self._rooms[code]["scores"].pop(pid, None)
            if not self._rooms[code]["participants"]:
                del self._rooms[code]


@st.cache_resource
def get_backend():
    if REDIS_URL:
        st.toast("☁️ Connected to Redis backend", icon="✅")
        return RedisBackend(REDIS_URL)
    return MemoryBackend()

DB = get_backend()

# ─── MediaPipe ────────────────────────────────────────────────────────────────
MODEL_PATH = Path("face_landmarker.task")
MODEL_URL  = ("https://storage.googleapis.com/mediapipe-models/"
              "face_landmarker/face_landmarker/float16/1/face_landmarker.task")

@st.cache_resource(show_spinner="⬇️ Downloading face model (first run only, ~6MB)…")
def _init_mediapipe():
    try:
        import mediapipe as _mp
        from mediapipe.tasks.python      import vision
        from mediapipe.tasks.python.core import base_options as bo
        if not MODEL_PATH.exists():
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        opts = vision.FaceLandmarkerOptions(
            base_options=bo.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
        )
        return vision.FaceLandmarker.create_from_options(opts), _mp
    except Exception:
        return None, None

_landmarker, mp = _init_mediapipe()
USE_MP = _landmarker is not None

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html,body,[class*="css"]  { font-family:'Space Grotesk',sans-serif; }
.stApp                    { background:#0a0e1a; color:#e2e8f0; }
[data-testid="stSidebar"] { background:#0f1629!important; border-right:1px solid #1e2d4a; }
[data-testid="stSidebar"] * { color:#cbd5e1!important; }
.main-header              { text-align:center; padding:1.5rem 0 1rem; }
.main-header h1           { font-size:2.2rem; font-weight:700;
    background:linear-gradient(135deg,#38bdf8,#818cf8,#a78bfa);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    letter-spacing:-0.02em; margin:0; }
.main-header p            { color:#64748b; font-size:.95rem; margin-top:.3rem; }
.score-card               { background:linear-gradient(135deg,#0f172a,#1e293b);
    border:1px solid #334155; border-radius:12px; padding:1rem 1.2rem; margin-bottom:.8rem; }
.score-label              { font-size:.75rem; font-weight:600; letter-spacing:.08em;
    text-transform:uppercase; color:#64748b; }
.score-value              { font-family:'JetBrains Mono',monospace; font-size:2.2rem;
    font-weight:600; line-height:1; margin-top:.2rem; }
.score-high{color:#34d399} .score-mid{color:#fbbf24} .score-low{color:#f87171}
.stTextInput input        { background:#1e293b!important; border:1px solid #334155!important;
    border-radius:8px!important; color:#e2e8f0!important; }
.stButton button          { background:linear-gradient(135deg,#3b82f6,#6366f1)!important;
    border:none!important; border-radius:8px!important; color:white!important;
    font-weight:600!important; width:100%; }
.focus-bar-container      { background:#1e293b; border-radius:999px; height:8px;
    width:100%; overflow:hidden; margin-top:.4rem; }
.focus-bar-fill           { height:100%; border-radius:999px; transition:width .5s ease; }
.status-dot               { display:inline-block; width:8px; height:8px; border-radius:50%;
    margin-right:6px; animation:pulse 2s infinite; }
.dot-green{background:#34d399} .dot-yellow{background:#fbbf24} .dot-red{background:#f87171}
@keyframes pulse          { 0%,100%{opacity:1} 50%{opacity:.4} }
.sidebar-section          { font-size:.7rem; font-weight:700; letter-spacing:.12em;
    text-transform:uppercase; color:#475569; padding:.8rem 0 .4rem;
    border-bottom:1px solid #1e293b; margin-bottom:.8rem; }
.metric-row               { display:flex; justify-content:space-between; align-items:center;
    padding:.35rem 0; border-bottom:1px solid #0f172a; font-size:.85rem; }
.metric-name{color:#94a3b8} .metric-val{font-family:'JetBrains Mono',monospace;font-weight:600}
.room-badge               { background:#1e293b; border:1px solid #334155; border-radius:8px;
    padding:.3rem .7rem; font-family:'JetBrains Mono',monospace; font-size:1rem;
    font-weight:700; color:#38bdf8; letter-spacing:.15em; display:inline-block; }
#MainMenu,footer,header   { visibility:hidden; }
.block-container          { padding-top:1rem!important; }
</style>
""", unsafe_allow_html=True)

# ─── Landmark helpers ─────────────────────────────────────────────────────────
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]
FACE_3D   = np.array([
    [0.,0.,0.],[0.,-330.,-65.],[-225.,170.,-135.],
    [225.,170.,-135.],[-150.,-150.,-125.],[150.,-150.,-125.],
], dtype=np.float64)
FACE_IDX = [1,152,263,33,287,57]

def _ear(lm,idx,w,h):
    pts=np.array([[lm[i].x*w,lm[i].y*h] for i in idx])
    return (np.linalg.norm(pts[1]-pts[5])+np.linalg.norm(pts[2]-pts[4]))/(2.*np.linalg.norm(pts[0]-pts[3])+1e-6)

def _pose(lm,w,h):
    pts=np.array([[lm[i].x*w,lm[i].y*h] for i in FACE_IDX],dtype=np.float64)
    cam=np.array([[w,0,w/2],[0,w,h/2],[0,0,1]],dtype=np.float64)
    ok,rv,_=cv2.solvePnP(FACE_3D,pts,cam,np.zeros((4,1)))
    if not ok: return 0.,0.
    rm,_=cv2.Rodrigues(rv); a,*_=cv2.RQDecomp3x3(rm)
    return a[1]*360,a[0]*360

@st.cache_resource
def _cascade():
    return cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")

# ─── Analyzer ────────────────────────────────────────────────────────────────
class ConcentrationAnalyzer:
    def __init__(self, room_code, pid):
        self.room_code=room_code; self.pid=pid
        self.ear_h=deque(maxlen=30); self.yaw_h=deque(maxlen=30); self.pit_h=deque(maxlen=30)
        self.blinks=0; self._bfrm=False; self.t0=time.time()
        self._last_push=0

    def _push(self, score, **kw):
        # Rate-limit Redis writes to max 2/sec
        now=time.time()
        if now-self._last_push < 0.5: return
        self._last_push=now
        DB.update_score(self.room_code, self.pid,
                        dict(score=score, **kw))

    def _mp(self, bgr):
        h,w=bgr.shape[:2]
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        img=mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb)
        res=_landmarker.detect(img)
        if not res.face_landmarks:
            self._push(0,ear=0,yaw=0,pitch=0,blink_rate=0,face_found=False)
            return bgr
        lm=res.face_landmarks[0]
        e=(_ear(lm,LEFT_EYE,w,h)+_ear(lm,RIGHT_EYE,w,h))/2
        self.ear_h.append(e)
        blink=0.
        if res.face_blendshapes:
            bs={b.category_name:b.score for b in res.face_blendshapes[0]}
            blink=(bs.get("eyeBlinkLeft",0)+bs.get("eyeBlinkRight",0))/2
        if blink>0.4 and not self._bfrm: self.blinks+=1; self._bfrm=True
        elif blink<=0.4: self._bfrm=False
        br=self.blinks/max(1,(time.time()-self.t0)/60)
        yaw,pit=_pose(lm,w,h)
        self.yaw_h.append(abs(yaw)); self.pit_h.append(abs(pit))
        eye_s=float(np.clip((np.mean(self.ear_h)-.15)/.15,0,1))*40
        pose_s=((np.clip(1-np.mean(self.yaw_h)/25,0,1)+np.clip(1-np.mean(self.pit_h)/20,0,1))/2)*40
        bl_s=(20. if 10<=br<=20 else float(np.clip(br/10,0,1))*20 if br<10 else float(np.clip(1-(br-20)/20,0,1))*20)
        score=int(eye_s+pose_s+bl_s)
        self._push(score,ear=round(e,3),yaw=round(yaw,1),pitch=round(pit,1),blink_rate=round(br,1),face_found=True)
        out=bgr.copy()
        c=(0,200,100) if score>=70 else (0,180,255) if score>=40 else (0,80,240)
        for idx in [LEFT_EYE,RIGHT_EYE]:
            pts=np.array([[int(lm[i].x*w),int(lm[i].y*h)] for i in idx])
            cv2.polylines(out,[pts],True,c,1)
        cv2.rectangle(out,(0,0),(160,40),(0,0,0),-1)
        cv2.putText(out,f"Focus: {score}%",(8,26),cv2.FONT_HERSHEY_SIMPLEX,.7,c,2)
        return out

    def _cv(self, bgr):
        gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
        faces=_cascade().detectMultiScale(gray,1.1,5,minSize=(80,80))
        if len(faces)==0:
            self._push(0,ear=0,yaw=0,pitch=0,blink_rate=0,face_found=False)
            cv2.putText(bgr,"No face",(8,26),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,80,240),2)
            return bgr
        x,y,fw,fh=faces[0]; h,w=bgr.shape[:2]
        score=int(np.clip((1-abs((x+fw/2)-w/2)/(w/2))*80+10,0,100))
        self._push(score,ear=0,yaw=0,pitch=0,blink_rate=0,face_found=True)
        c=(0,200,100) if score>=70 else (0,180,255) if score>=40 else (0,80,240)
        cv2.rectangle(bgr,(x,y),(x+fw,y+fh),c,2)
        cv2.rectangle(bgr,(0,0),(175,40),(0,0,0),-1)
        cv2.putText(bgr,f"Focus: {score}%",(8,26),cv2.FONT_HERSHEY_SIMPLEX,.7,c,2)
        return bgr

    def process(self,bgr):
        return self._mp(bgr) if USE_MP else self._cv(bgr)

# ─── Session state ────────────────────────────────────────────────────────────
for k,v in [("joined",False),("room_code",""),("my_pid",""),
            ("my_name",""),("analyzer",None)]:
    if k not in st.session_state: st.session_state[k]=v

def leave_room():
    DB.remove_participant(st.session_state.room_code, st.session_state.my_pid)
    for k,v in [("joined",False),("room_code",""),("my_pid",""),
                ("my_name",""),("analyzer",None)]:
        st.session_state[k]=v

# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN A — Join / Create room
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.joined:
    st.markdown("""<div class="main-header"><h1>🎯 FocusMeet</h1>
      <p>Real-time concentration detection for your meetings</p></div>""",
      unsafe_allow_html=True)

    _,col,_ = st.columns([1,2,1])
    with col:
        st.markdown("""<div style="background:#0f172a;border:1px solid #334155;
            border-radius:16px;padding:2rem;margin-top:1rem">
          <div style="font-size:.9rem;font-weight:600;color:#94a3b8;margin-bottom:1.2rem;
                      text-align:center;letter-spacing:.05em">JOIN A MEETING</div>
        """, unsafe_allow_html=True)

        name_in = st.text_input("Your name", placeholder="Alice", key="ni")
        room_in = st.text_input("Room code",
            placeholder="Leave empty to create a new room", key="ri")

        c1,c2 = st.columns(2)
        join_btn   = c1.button("🚪 Join room",  use_container_width=True)
        create_btn = c2.button("✨ New room",    use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Backend status badge
        if REDIS_URL:
            st.markdown('<div style="text-align:center;margin-top:.5rem;font-size:.75rem;color:#34d399">'
                        '☁️ Cloud mode — rooms shared across all users</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="text-align:center;margin-top:.5rem;font-size:.75rem;color:#fbbf24">'
                        '💻 Local mode — set REDIS_URL for cloud sharing</div>', unsafe_allow_html=True)

        if join_btn or create_btn:
            name = name_in.strip()
            if not name:
                st.error("Please enter your name.")
            else:
                if create_btn or not room_in.strip():
                    import random, string
                    code = "".join(random.choices(string.ascii_uppercase+string.digits, k=6))
                else:
                    code = room_in.strip().upper()
                    if not DB.room_exists(code):
                        st.error(f"Room **{code}** not found. Check the code or create a new room.")
                        st.stop()

                pid = str(int(time.time()*1000) % 1000000)
                DB.add_participant(code, pid, name)
                st.session_state.room_code = code
                st.session_state.my_pid    = pid
                st.session_state.my_name   = name
                st.session_state.analyzer  = ConcentrationAnalyzer(code, pid)
                st.session_state.joined    = True
                st.rerun()
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# SCREEN B — Inside room
# ═══════════════════════════════════════════════════════════════════════════════
room_code = st.session_state.room_code
my_pid    = st.session_state.my_pid
room      = DB.get_room(room_code) or {"participants":{}, "scores":{}}
parts     = room.get("participants", {})
scores    = room.get("scores", {})

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:1rem 0 .5rem">'
                '<span style="font-size:1.6rem">🎯</span>'
                '<div style="font-size:1.1rem;font-weight:700;color:#38bdf8">FocusMeet</div>'
                '</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="text-align:center;margin-bottom:.5rem">'
                f'<span style="font-size:.65rem;color:#475569;letter-spacing:.1em">ROOM CODE</span><br>'
                f'<span class="room-badge">{room_code}</span></div>', unsafe_allow_html=True)
    st.divider()
    st.markdown('<div class="sidebar-section">📊 Live Analytics</div>', unsafe_allow_html=True)

    for pid,pname in parts.items():
        s     = scores.get(pid,{})
        score = s.get("score",0) if s.get("face_found") else 0
        cc = "score-high" if score>=70 else "score-mid" if score>=40 else "score-low"
        dc = "dot-green"  if score>=70 else "dot-yellow" if score>=40 else "dot-red"
        bc = "#34d399"    if score>=70 else "#fbbf24"    if score>=40 else "#f87171"
        me = " 👈" if pid==my_pid else ""
        st_ = ("Focused" if score>=70 else "Distracted" if score>=40 else "Absent") \
              if s.get("face_found") else "Waiting…"
        st.markdown(f"""<div class="score-card">
          <div class="score-label"><span class="status-dot {dc}"></span>{pname}{me}</div>
          <div class="score-value {cc}">{score}<span style="font-size:1rem;color:#64748b">%</span></div>
          <div style="color:#64748b;font-size:.75rem;margin-top:2px">{st_}</div>
          <div class="focus-bar-container">
            <div class="focus-bar-fill" style="width:{score}%;background:{bc}"></div>
          </div></div>""", unsafe_allow_html=True)
        if USE_MP:
            with st.expander(f"📈 {pname}"):
                st.markdown(f"""
                <div class="metric-row"><span class="metric-name">EAR</span>
                <span class="metric-val" style="color:#38bdf8">{s.get('ear',0):.3f}</span></div>
                <div class="metric-row"><span class="metric-name">Yaw</span>
                <span class="metric-val">{s.get('yaw',0):.1f}°</span></div>
                <div class="metric-row"><span class="metric-name">Pitch</span>
                <span class="metric-val">{s.get('pitch',0):.1f}°</span></div>
                <div class="metric-row"><span class="metric-name">Blinks/min</span>
                <span class="metric-val">{s.get('blink_rate',0):.1f}</span></div>
                """, unsafe_allow_html=True)

    st.divider()
    vals = [s.get("score",0) for s in scores.values() if s.get("face_found")]
    avg  = int(np.mean(vals)) if vals else 0
    bc   = "#34d399" if avg>=70 else "#fbbf24" if avg>=40 else "#f87171"
    st.markdown(f"""<div class="sidebar-section">🏁 Meeting Average</div>
    <div style="text-align:center;padding:.5rem 0">
      <div style="font-family:'JetBrains Mono',monospace;font-size:3rem;font-weight:700;
                  color:{bc};line-height:1">{avg}<span style="font-size:1.2rem;color:#64748b">%</span></div>
      <div style="color:#64748b;font-size:.8rem">group focus score</div>
    </div>""", unsafe_allow_html=True)
    st.divider()
    st.markdown("""<div class="sidebar-section">ℹ️ Legend</div>
    <div style="font-size:.8rem;line-height:2.2">
      <span class="status-dot dot-green"></span><span style="color:#34d399">70–100%</span> Focused<br>
      <span class="status-dot dot-yellow"></span><span style="color:#fbbf24">40–69%</span> Distracted<br>
      <span class="status-dot dot-red"></span><span style="color:#f87171">0–39%</span> Not present
    </div>""", unsafe_allow_html=True)
    st.divider()
    if st.button("🚪 Leave room", use_container_width=True):
        leave_room(); st.rerun()

# ─── Main ─────────────────────────────────────────────────────────────────────
st.markdown(f"""<div class="main-header"><h1>🎯 FocusMeet</h1>
  <p>Room <span class="room-badge" style="font-size:.85rem">{room_code}</span>
  &nbsp;·&nbsp; {len(parts)} participant(s)</p></div>""", unsafe_allow_html=True)

st.info(f"📋 Share this code with others: **{room_code}**", icon="📡")
st.divider()

# My camera
az    = st.session_state.analyzer
my_s  = scores.get(my_pid,{})
score = my_s.get("score",0) if my_s.get("face_found") else 0
color = "#34d399" if score>=70 else "#fbbf24" if score>=40 else "#f87171"

st.markdown(f"""<div style="max-width:620px;margin:0 auto">
  <div style="background:#0f172a;border:2px solid #1e293b;border-radius:12px;
              padding:.6rem .8rem;margin-bottom:.5rem;
              display:flex;align-items:center;justify-content:space-between">
    <div style="font-weight:600">📷 {st.session_state.my_name} (you)</div>
    <div style="font-family:'JetBrains Mono',monospace;font-weight:700;color:{color}">{score}%</div>
  </div></div>""", unsafe_allow_html=True)

cam_col, _ = st.columns([2,1])
with cam_col:
    def my_cb(frame):
        img=frame.to_ndarray(format="bgr24")
        return av.VideoFrame.from_ndarray(az.process(img),format="bgr24")
    webrtc_streamer(
        key=f"cam_{my_pid}",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTCConfiguration({"iceServers":[{"urls":["stun:stun.l.google.com:19302"]}]}),
        video_frame_callback=my_cb,
        media_stream_constraints={"video":True,"audio":False},
        async_processing=True,
    )

# Other participants
others = [(pid,name) for pid,name in parts.items() if pid!=my_pid]
if others:
    st.divider()
    st.markdown('<div style="font-size:.8rem;font-weight:700;letter-spacing:.1em;'
                'text-transform:uppercase;color:#475569;margin-bottom:.8rem">👥 Other participants</div>',
                unsafe_allow_html=True)
    cols = st.columns(min(len(others),4))
    for i,(pid,name) in enumerate(others):
        s     = scores.get(pid,{})
        score = s.get("score",0) if s.get("face_found") else 0
        color = "#34d399" if score>=70 else "#fbbf24" if score>=40 else "#f87171"
        dc    = "dot-green" if score>=70 else "dot-yellow" if score>=40 else "dot-red"
        st_   = ("Focused" if score>=70 else "Distracted" if score>=40 else "Absent") \
                if s.get("face_found") else "Waiting…"
        with cols[i%len(cols)]:
            st.markdown(f"""<div style="background:#0f172a;border:1px solid #1e293b;
                border-radius:12px;padding:1rem;text-align:center">
              <div style="font-size:2rem">👤</div>
              <div style="font-weight:600;margin:.3rem 0">{name}</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:1.8rem;
                          font-weight:700;color:{color}">{score}%</div>
              <div style="font-size:.75rem;color:#64748b;margin-top:.2rem">
                <span class="status-dot {dc}"></span>{st_}</div>
              <div class="focus-bar-container" style="margin-top:.6rem">
                <div class="focus-bar-fill" style="width:{score}%;background:{color}"></div>
              </div></div>""", unsafe_allow_html=True)

# Auto-refresh every 3s
st.markdown("<script>setTimeout(()=>window.location.reload(),3000)</script>",
            unsafe_allow_html=True)
