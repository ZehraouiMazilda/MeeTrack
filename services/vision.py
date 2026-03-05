import cv2
import numpy as np
import time
import threading
from collections import deque

try:
    import mediapipe as mp
    _face_mesh = mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.3,
        min_tracking_confidence=0.3,
    )
    MP_OK = True
except Exception as e:
    MP_OK = False
    _face_mesh = None

# ── Landmarks ─────────────────────────────────────────────────
LEFT_EYE   = [33,  160, 158, 133, 153, 144]
RIGHT_EYE  = [263, 387, 385, 362, 380, 373]
# Bouche : lèvre haute, lèvre basse, coins gauche/droite
MOUTH_TOP    = 13
MOUTH_BOTTOM = 14
MOUTH_LEFT   = 78
MOUTH_RIGHT  = 308
NOSE_TIP     = 1
LEFT_EAR_PT  = 234
RIGHT_EAR_PT = 454
CHIN         = 152
FOREHEAD     = 10

# ── Seuils fixes (overridés par calibration) ──────────────────
YAW_THRESHOLD      = 35.0
PITCH_UP_THRESHOLD = 30.0
ALERT_DELAY        = 15.0
ALERT_COOLDOWN     = 45.0
BLINK_MIN_DURATION = 0.08   # secondes — en dessous = clignement normal
BLINK_MAX_DURATION = 0.40   # au dessus = yeux vraiment fermés
YAWN_MAR_THRESHOLD = 0.55   # MAR au dessus = bâillement
YAWN_DURATION      = 2.0    # secondes bouche ouverte = bâillement

# ── Shared state ──────────────────────────────────────────────
class ConcentrationState:
    def __init__(self):
        self.lock = threading.Lock()

        # Métriques live
        self.score         = 100
        self.ear           = 0.30
        self.mar           = 0.0
        self.yaw           = 0.0
        self.pitch         = 0.0
        self.face_detected = False
        self.alert         = ""
        self.alert_type    = ""
        self.is_speaking   = False   # bouche ouverte en mouvement = parle
        self.is_yawning    = False

        # Calibration
        self.calibrated        = False
        self.calibrating       = False
        self.calib_ear_samples = []
        self.ear_threshold     = 0.20   # seuil par défaut, remplacé après calibration
        self.ear_natural       = 0.30   # EAR naturel de la personne

        # Historique lissage (60 frames)
        self._score_history = deque(maxlen=60)

        # Timestamps
        self._eye_closed_start  = None   # début fermeture yeux
        self._eye_closed_dur    = 0.0    # durée fermeture courante
        self._yaw_since         = None
        self._no_face_since     = None
        self._pitch_up_since    = None
        self._mouth_open_since  = None
        self._last_alert_sound  = 0.0

        # Stats session
        self.blink_count        = 0
        self.yawn_count         = 0
        self.distraction_events = []

shared_state = ConcentrationState()


# ── Son ───────────────────────────────────────────────────────
def _play_alert(message: str):
    """Délègue le TTS au voice_detector — bloqué si Lumi est en mode actif."""
    try:
        from services.voice_detector import play_tts, get_status
        vs = get_status()
        # Bloquer seulement si Lumi parle activement (pas pendant mode actif)
        if vs.get("is_speaking"):
            return
        play_tts(message)
    except Exception:
        def _beep():
            try:
                import winsound
                winsound.Beep(880, 300)
            except: pass
        threading.Thread(target=_beep, daemon=True).start()


def _trigger_alert(msg: str, atype: str):
    now = time.time()
    with shared_state.lock:
        shared_state.alert      = f"🚨 {msg}"
        shared_state.alert_type = atype
        last                    = shared_state._last_alert_sound
        shared_state.distraction_events.append({
            "type": atype, "msg": msg, "time": now
        })
    if now - last > ALERT_COOLDOWN:
        with shared_state.lock:
            shared_state._last_alert_sound = now
        clean = msg.replace("🚨","").replace("👤","").strip()
        _play_alert(clean)


# ── Calibration ───────────────────────────────────────────────
def start_calibration():
    """Lance une calibration de 3 secondes."""
    with shared_state.lock:
        shared_state.calibrating       = True
        shared_state.calibrated        = False
        shared_state.calib_ear_samples = []


def _finish_calibration():
    samples = shared_state.calib_ear_samples
    if len(samples) < 10:
        return
    ear_natural = float(np.percentile(samples, 70))  # 70e percentile = yeux normalement ouverts
    ear_natural = max(0.18, min(0.40, ear_natural))   # bornes de sécurité
    ear_threshold = ear_natural * 0.68                # -32% = yeux fermés
    with shared_state.lock:
        shared_state.ear_natural   = round(ear_natural, 3)
        shared_state.ear_threshold = round(ear_threshold, 3)
        shared_state.calibrating   = False
        shared_state.calibrated    = True


# ── Calculs ───────────────────────────────────────────────────
def _ear_val(pts: np.ndarray) -> float:
    A = np.linalg.norm(pts[1] - pts[5])
    B = np.linalg.norm(pts[2] - pts[4])
    C = np.linalg.norm(pts[0] - pts[3])
    return (A + B) / (2.0 * C + 1e-6)


def _mar_val(lms, w, h) -> float:
    """Mouth Aspect Ratio — grand = bouche ouverte."""
    top    = np.array([lms[MOUTH_TOP].x    * w, lms[MOUTH_TOP].y    * h])
    bottom = np.array([lms[MOUTH_BOTTOM].x * w, lms[MOUTH_BOTTOM].y * h])
    left   = np.array([lms[MOUTH_LEFT].x   * w, lms[MOUTH_LEFT].y   * h])
    right  = np.array([lms[MOUTH_RIGHT].x  * w, lms[MOUTH_RIGHT].y  * h])
    vert   = np.linalg.norm(top - bottom)
    horiz  = np.linalg.norm(left - right)
    return float(vert / (horiz + 1e-6))


def _head_pose(lms, w, h):
    def pt(i): return np.array([lms[i].x*w, lms[i].y*h, lms[i].z*w])
    nose      = pt(NOSE_TIP)
    left_ear  = pt(LEFT_EAR_PT)
    right_ear = pt(RIGHT_EAR_PT)
    chin      = pt(CHIN)
    forehead  = pt(FOREHEAD)

    ear_mid    = (left_ear + right_ear) / 2
    face_width = np.linalg.norm(right_ear - left_ear)
    yaw        = float(np.degrees(np.arctan2(nose[0] - ear_mid[0], face_width/2 + 1e-6)))

    vert      = forehead - chin
    nose_proj = nose - chin
    norm_v    = np.linalg.norm(vert)
    norm_n    = np.linalg.norm(nose_proj)
    if norm_v > 0 and norm_n > 0:
        cos_a = np.clip(np.dot(nose_proj, vert) / (norm_n * norm_v), -1, 1)
        raw   = np.degrees(np.arccos(cos_a)) - 90
    else:
        raw = 0.0
    face_mid_y = (forehead[1] + chin[1]) / 2
    pitch = float(-raw if nose[1] < face_mid_y else raw)  # positif = tête levée, négatif = tête baissée
    return yaw, pitch


def _compute_score(ear_v, yaw_v, pitch_v, face_ok, ear_thresh, ear_nat):
    """
    Score pondéré réaliste :
      EAR   → 40 pts  (proportionnel entre seuil et naturel)
      Yaw   → 40 pts  (tolérance ±15°, dégradé jusqu'à ±28°)
      Pitch → 20 pts  (vers le bas = plein, vers le haut = dégradé)
    Max théorique ≈ 88 pts (personne parfaite n'existe pas)
    """
    if not face_ok:
        return 0

    # EAR (40 pts)
    if ear_v >= ear_nat:
        ear_score = 40
    elif ear_v >= ear_thresh:
        ear_score = int(40 * (ear_v - ear_thresh) / (ear_nat - ear_thresh + 1e-6))
    else:
        ear_score = 0

    # Yaw (40 pts)
    yaw_abs = abs(yaw_v)
    if yaw_abs <= 12:
        yaw_score = 40
    elif yaw_abs <= YAW_THRESHOLD:
        yaw_score = int(40 * (1 - (yaw_abs - 12) / (YAW_THRESHOLD - 12)))
    else:
        yaw_score = 0

    # Pitch (20 pts) — négatif = tête baissée (notes) = bien, positif = tête levée = mal
    if pitch_v <= 15:
        pitch_score = 20          # position normale à légèrement levée → plein
    elif pitch_v <= PITCH_UP_THRESHOLD:
        pitch_score = int(20 * (1 - (pitch_v - 15) / (PITCH_UP_THRESHOLD - 15)))
    else:
        pitch_score = 0

    return ear_score + yaw_score + pitch_score


def _smooth(raw: int) -> int:
    shared_state._score_history.append(raw)
    if len(shared_state._score_history) < 5:
        return raw
    # Moyenne pondérée : frames récentes comptent plus
    hist   = list(shared_state._score_history)
    n      = len(hist)
    weights= np.linspace(0.5, 1.0, n)
    return int(np.average(hist, weights=weights))


def _bgr(score):
    if score > 70: return (34, 197, 94)
    if score > 45: return (59, 130, 246)
    return (59, 59, 239)


# ── MAIN : traitement frame ────────────────────────────────────
def process_frame(img: np.ndarray) -> np.ndarray:
    if _face_mesh is None:
        cv2.putText(img, "MediaPipe non disponible", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        return img

    h, w = img.shape[:2]
    rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    res  = _face_mesh.process(rgb)
    now  = time.time()

    # ── Pas de visage ──────────────────────────────────────────
    if not res.multi_face_landmarks:
        with shared_state.lock:
            if shared_state._no_face_since is None:
                shared_state._no_face_since = now
            elapsed                    = now - shared_state._no_face_since
            shared_state.face_detected = False
            shared_state.score         = _smooth(0)
            shared_state._eye_closed_start = None
            shared_state._yaw_since        = None
            shared_state._pitch_up_since   = None

        if elapsed > ALERT_DELAY:
            import random
            NO_FACE_MSGS = [
                "T'es devenu Casper ou quoi ?",
                f"Où t'es passé depuis {int(elapsed)} secondes ? Y'a plus personne !",
                "La caméra te cherche... t'as disparu comme mes chances de réussir !",
                "Reviens ! La caméra se sent seule !",
                "T'es parti faire un tour ? Tes cours t'attendent !",
                "Signal perdu, t'es en mode fantôme ?",
            ]
            _trigger_alert(random.choice(NO_FACE_MSGS), "no_face")

        cv2.rectangle(img, (0, 0), (w, 52), (15, 15, 30), -1)
        cv2.putText(img, "Aucun visage detecte", (12, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (80, 80, 239), 2, cv2.LINE_AA)
        return img

    lms = res.multi_face_landmarks[0].landmark

    def pts2d(idx_list):
        return np.array([[lms[i].x * w, lms[i].y * h] for i in idx_list])

    ear_v   = (_ear_val(pts2d(LEFT_EYE)) + _ear_val(pts2d(RIGHT_EYE))) / 2.0
    mar_v   = _mar_val(lms, w, h)
    yaw_v, pitch_v = _head_pose(lms, w, h)

    with shared_state.lock:
        ear_thresh = shared_state.ear_threshold
        ear_nat    = shared_state.ear_natural
        calibrating = shared_state.calibrating
        calibrated  = shared_state.calibrated

    # ── Calibration en cours ───────────────────────────────────
    if calibrating:
        with shared_state.lock:
            shared_state.calib_ear_samples.append(ear_v)
            n = len(shared_state.calib_ear_samples)
        if n >= 90:  # ~3 secondes à 30fps
            _finish_calibration()
            with shared_state.lock:
                ear_thresh = shared_state.ear_threshold
                ear_nat    = shared_state.ear_natural
        # Affichage calibration
        cv2.rectangle(img, (0, 0), (w, 52), (15, 15, 30), -1)
        pct = min(100, int(n / 90 * 100))
        cv2.putText(img, f"Calibration... {pct}%", (12, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (59, 200, 245), 2, cv2.LINE_AA)
        bar_w = int((w - 24) * pct / 100)
        cv2.rectangle(img, (12, 43), (w-12, 50), (50, 50, 60), -1)
        cv2.rectangle(img, (12, 43), (12+bar_w, 50), (59, 200, 245), -1)
        return img

    # ── Détection clignement ───────────────────────────────────
    eyes_closed = ear_v < ear_thresh
    if eyes_closed:
        if shared_state._eye_closed_start is None:
            shared_state._eye_closed_start = now
        eye_closed_dur = now - shared_state._eye_closed_start
    else:
        # Yeux viennent de s'ouvrir
        if shared_state._eye_closed_start is not None:
            dur = now - shared_state._eye_closed_start
            if BLINK_MIN_DURATION <= dur <= BLINK_MAX_DURATION:
                with shared_state.lock:
                    shared_state.blink_count += 1
        shared_state._eye_closed_start = None
        eye_closed_dur = 0.0

    with shared_state.lock:
        shared_state._eye_closed_dur = eye_closed_dur

    # ── Détection bâillement ───────────────────────────────────
    mouth_open = mar_v > YAWN_MAR_THRESHOLD
    if mouth_open:
        if shared_state._mouth_open_since is None:
            shared_state._mouth_open_since = now
        mouth_dur = now - shared_state._mouth_open_since
        is_yawning = mouth_dur > YAWN_DURATION
    else:
        if shared_state._mouth_open_since is not None:
            shared_state._mouth_open_since = None
        mouth_dur  = 0.0
        is_yawning = False

    with shared_state.lock:
        shared_state.is_yawning  = is_yawning
        shared_state.mar         = round(mar_v, 3)
        shared_state.is_speaking = 0.15 < mar_v < YAWN_MAR_THRESHOLD

    # (notify_mouth_moving supprimé — non utilisé)

    # ── Score ──────────────────────────────────────────────────
    # Pénalité si yeux vraiment fermés > 400ms (pas juste un clignement)
    ear_for_score = ear_nat if eye_closed_dur < BLINK_MAX_DURATION else ear_v
    raw     = _compute_score(ear_for_score, yaw_v, pitch_v, True, ear_thresh, ear_nat)
    # Pénalité bâillement
    if is_yawning:
        raw = max(0, raw - 15)
    smoothed = _smooth(raw)

    # ── Alertes ────────────────────────────────────────────────
    alert_msg  = ""
    alert_type = ""

    # Yeux fermés > 5s (pas un clignement)
    if eye_closed_dur > 8.0:
        alert_msg  = f"Tu dors ? Yeux fermés depuis {int(eye_closed_dur)} secondes !"
        alert_type = "eyes"

    # Bâillement
    if is_yawning and not alert_msg:
        alert_msg  = "Bâillement détecté, tu fatigues, fais une pause !"
        alert_type = "yawn"

    # Tête tournée > 10s
    if abs(yaw_v) > YAW_THRESHOLD:
        if shared_state._yaw_since is None:
            shared_state._yaw_since = now
        elapsed_y = now - shared_state._yaw_since
        if elapsed_y > 20.0 and not alert_msg:
            d          = "droite" if yaw_v > 0 else "gauche"
            alert_msg  = f"Hé ! Concentre-toi, tu regardes à {d} !"
            alert_type = "yaw"
    else:
        shared_state._yaw_since = None

    # Tête levée > 10s (pitch positif élevé = regarde vraiment en haut)
    if pitch_v > PITCH_UP_THRESHOLD:
        if shared_state._pitch_up_since is None:
            shared_state._pitch_up_since = now
        elapsed_p = now - shared_state._pitch_up_since
        if elapsed_p > ALERT_DELAY and not alert_msg:
            alert_msg  = "Hé ! Baisse la tête et concentre-toi !"
            alert_type = "pitch"
    else:
        shared_state._pitch_up_since = None

    if alert_msg:
        _trigger_alert(alert_msg, alert_type)

    # ── Mise à jour state ──────────────────────────────────────
    with shared_state.lock:
        shared_state.face_detected  = True
        shared_state.ear            = round(ear_v, 3)
        shared_state.yaw            = round(yaw_v, 1)
        shared_state.pitch          = round(pitch_v, 1)
        shared_state.score          = smoothed
        # Popup disparaît automatiquement si plus d'alerte
        shared_state.alert          = f"🚨 {alert_msg}" if alert_msg else ""
        shared_state.alert_type     = alert_type if alert_msg else ""
        shared_state._no_face_since = None

    # ── Dessin ────────────────────────────────────────────────
    color = _bgr(smoothed)

    # Bande haut
    cv2.rectangle(img, (0, 0), (w, 52), (20, 20, 30), -1)
    cv2.putText(img, f"Concentration: {smoothed}%", (12, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)
    bar_w = int((w - 24) * smoothed / 100)
    cv2.rectangle(img, (12, 43), (w-12, 50), (50, 50, 60), -1)
    cv2.rectangle(img, (12, 43), (12+bar_w, 50), color, -1)

    # Points yeux (couleur selon EAR vs seuil calibré)
    eye_col = (34, 197, 94) if not eyes_closed else (59, 59, 239)
    for i in LEFT_EYE + RIGHT_EYE:
        cv2.circle(img, (int(lms[i].x*w), int(lms[i].y*h)), 2, eye_col, -1)

    # Contour bouche (couleur selon MAR)
    mouth_col = (59, 200, 245) if is_yawning else (200, 200, 200)
    for i in [MOUTH_TOP, MOUTH_BOTTOM, MOUTH_LEFT, MOUTH_RIGHT]:
        cv2.circle(img, (int(lms[i].x*w), int(lms[i].y*h)), 3, mouth_col, -1)

    # Ligne nez→oreilles (yaw)
    nose_pt  = (int(lms[NOSE_TIP].x*w),      int(lms[NOSE_TIP].y*h))
    lear_pt  = (int(lms[LEFT_EAR_PT].x*w),   int(lms[LEFT_EAR_PT].y*h))
    rear_pt  = (int(lms[RIGHT_EAR_PT].x*w),  int(lms[RIGHT_EAR_PT].y*h))
    mid_pt   = ((lear_pt[0]+rear_pt[0])//2,   (lear_pt[1]+rear_pt[1])//2)
    yaw_col  = (34, 197, 94) if abs(yaw_v) < YAW_THRESHOLD else (59, 59, 239)
    cv2.line(img, mid_pt, nose_pt, yaw_col, 2, cv2.LINE_AA)
    cv2.circle(img, nose_pt, 5, yaw_col, -1)

    # Bas : métriques
    cv2.rectangle(img, (0, h-30), (w, h), (20, 20, 30), -1)
    ear_col  = (34, 197, 94) if not eyes_closed else (59, 59, 239)
    yaw_col2 = (34, 197, 94) if abs(yaw_v) < YAW_THRESHOLD else (59, 59, 239)
    cv2.putText(img, f"EAR:{ear_v:.2f}(s:{ear_thresh:.2f})", (8, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, ear_col, 1, cv2.LINE_AA)
    cv2.putText(img, f"Yaw:{yaw_v:+.0f}", (w//2-30, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, yaw_col2, 1, cv2.LINE_AA)
    cv2.putText(img, f"MAR:{mar_v:.2f}", (w-80, h-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, mouth_col, 1, cv2.LINE_AA)

    # Flash rouge si alerte
    if alert_msg:
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 200), -1)
        cv2.addWeighted(overlay, 0.12, img, 0.88, 0, img)

    return img