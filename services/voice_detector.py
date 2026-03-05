"""
Voice Detector — écoute continue, déclenche sur "Lumi", stop sur "merci Lumi"
"""
import threading
import time
import os
import io
import json
import numpy as np
from dotenv import load_dotenv
load_dotenv()

_DIR = os.path.dirname(os.path.abspath(__file__))
_WAV = os.path.join(_DIR, "chunk.wav")

def _get_groq():
    import httpx
    from groq import Groq
    return Groq(api_key=os.getenv("GROQ_API_KEY"), http_client=httpx.Client(verify=True))

class VoiceState:
    def __init__(self):
        self.lock            = threading.Lock()
        self.running         = False
        self.is_recording    = False
        self.is_speaking     = False  # Lumi parle → micro off
        self.lumi_mode            = False
        self.last_transcript      = ""
        self.last_lumi_activity   = 0.0   # timestamp dernière question en mode Lumi
        self.thread_id            = None  # ID du thread actif
        self.session_theme   = "général"
        self.alert           = ""
        self.transcript_log  = []

voice_state = VoiceState()
_on_lumi_question = None
_on_alert = None

def set_callbacks(on_lumi_question=None, on_alert=None):
    global _on_lumi_question, _on_alert
    _on_lumi_question = on_lumi_question
    _on_alert = on_alert

def play_tts(text: str):
    def _run():
        tmp = None
        with voice_state.lock:
            voice_state.is_speaking = True
        try:
            from gtts import gTTS
            import tempfile, subprocess
            buf = io.BytesIO()
            gTTS(text=str(text)[:150], lang='fr', slow=False).write_to_fp(buf)
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(buf.getvalue())
                tmp = f.name
            ps = (
                "Add-Type -AssemblyName presentationCore; "
                "$mp = New-Object System.Windows.Media.MediaPlayer; "
                f"$mp.Open([uri]'{tmp}'); "
                "$mp.Play(); "
                "Start-Sleep 1; "
                "$dur = $mp.NaturalDuration.TimeSpan.TotalSeconds; "
                "if($dur -gt 0){ Start-Sleep ([int]$dur + 1) }else{ Start-Sleep 10 }; "
                "$mp.Stop(); $mp.Close()"
            )
            subprocess.run(['powershell', '-NoProfile', '-c', ps],
                           timeout=60, capture_output=True)
        except Exception:
            try:
                import winsound
                winsound.Beep(880, 150)
            except: pass
        finally:
            with voice_state.lock:
                voice_state.is_speaking = False
                # Reset le timer inactivité après que Lumi finit de parler
                if voice_state.lumi_mode:
                    voice_state.last_lumi_activity = time.time()
            if tmp:
                try: os.unlink(tmp)
                except: pass
    threading.Thread(target=_run, daemon=True).start()

def start_listening():
    # Vérifier si un thread "lumi-voice-loop" est déjà vivant dans ce process
    for t in threading.enumerate():
        if t.name == "lumi-voice-loop" and t.is_alive():
            print(f"[VOICE] Thread déjà vivant (id={t.ident}), skip", flush=True)
            with voice_state.lock:
                voice_state.running = True
                voice_state.thread_id = t.ident
            return

    with voice_state.lock:
        voice_state.running = True

    t = threading.Thread(target=_loop, daemon=True, name="lumi-voice-loop")
    t.start()
    with voice_state.lock:
        voice_state.thread_id = t.ident
    print(f"[VOICE] Nouveau thread démarré (id={t.ident})", flush=True)

def stop_listening():
    with voice_state.lock:
        voice_state.running = False
        voice_state.thread_id = None

_HALLUCINATIONS = [
    "thank you for watching", "thanks for watching",
    "sous-titres", "subtitles by", "transcribed by", "amara.org",
    "société radio-canada", "radio-canada", "sous-titrage",
    "bip", "♪", "[music]", "[silence]",
]

_WAKE = ["lumi", "loumi", "loumy", "lumy", "lumie", "lomy"]

def _loop():
    import sounddevice as sd
    import soundfile as sf

    SAMPLERATE = 16000
    DURATION   = 10  # secondes

    LUMI_IDLE_TIMEOUT = 30.0  # secondes avant message d'au revoir

    while True:
        with voice_state.lock:
            if not voice_state.running:
                break
            speaking      = voice_state.is_speaking
            lumi_active   = voice_state.lumi_mode
            last_activity = voice_state.last_lumi_activity

        # Timeout inactivité Lumi — seulement si pas en train d'enregistrer/parler
        with voice_state.lock:
            is_rec  = voice_state.is_recording
            is_spk  = voice_state.is_speaking
        if lumi_active and last_activity > 0 and not is_rec and not is_spk:
            idle = time.time() - last_activity
            if idle > LUMI_IDLE_TIMEOUT:
                with voice_state.lock:
                    voice_state.lumi_mode = False
                    voice_state.last_lumi_activity = 0.0
                import random
                BYE_MSGS = [
                    "Je vois que t'as plus besoin de moi, à tout à l'heure !",
                    "Ok je te laisse travailler, appelle-moi si t'as besoin !",
                    "Je disparais, dis Lumi quand tu veux me parler !",
                    "Je vois que t'es concentré, je te laisse !",
                ]
                play_tts(random.choice(BYE_MSGS))

        if speaking:
            time.sleep(0.3)
            continue

        try:
            with voice_state.lock:
                voice_state.is_recording = True

            audio = sd.rec(int(DURATION * SAMPLERATE),
                           samplerate=SAMPLERATE, channels=1, dtype='float32')
            sd.wait()

            with voice_state.lock:
                voice_state.is_recording = False
                was_speaking = voice_state.is_speaking

            # Jeter le chunk si Lumi a parlé pendant l enregistrement
            if was_speaking:
                continue

            rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
            if rms < 0.008:
                continue

            sf.write(_WAV, audio, SAMPLERATE)
            if os.path.getsize(_WAV) < 1000:
                continue

            _transcribe(_WAV)

        except Exception as e:
            with voice_state.lock:
                voice_state.is_recording = False
                voice_state.last_transcript = f"[Erreur: {e}]"
            time.sleep(1)

def _transcribe(path: str):
    try:
        groq = _get_groq()
        with open(path, "rb") as f:
            res = groq.audio.transcriptions.create(
                file=(os.path.basename(path), f),
                model="whisper-large-v3",
                language="fr",
                response_format="verbose_json",
                prompt="français, darija algérienne, kabyle"
            )
        text = (res.text or "").strip()
        print(f"[VOICE] '{text}'", flush=True)

        if not text:
            return
        # Rejeter les transcriptions trop courtes (< 3 mots = hallucination)
        words = [w for w in text.strip().split() if len(w) > 1]
        if len(words) < 2:
            print(f"[VOICE] Rejeté (trop court): '{text}'", flush=True)
            return
        # Rejeter si trop de lettres isolées (ex: "U S H E")
        single_letters = sum(1 for w in text.strip().split() if len(w) == 1)
        if single_letters >= 3:
            print(f"[VOICE] Rejeté (lettres isolées): '{text}'", flush=True)
            return
        if any(h in text.lower() for h in _HALLUCINATIONS):
            return

        with voice_state.lock:
            voice_state.last_transcript = text

        tl = text.lower()

        # "merci Lumi" → désactive
        if "merci" in tl and any(w in tl for w in _WAKE):
            with voice_state.lock:
                voice_state.lumi_mode = False
            print("[VOICE] Mode Lumi désactivé", flush=True)
            play_tts("D'accord, à bientôt !")
            return
        # "merci" seul en mode actif → désactive aussi
        with voice_state.lock:
            active = voice_state.lumi_mode
        if active and "merci" in tl:
            with voice_state.lock:
                voice_state.lumi_mode = False
            play_tts("D'accord, à bientôt !")
            return

        # Wake word → active + répond si question dans la même phrase
        if any(w in tl for w in _WAKE):
            with voice_state.lock:
                voice_state.lumi_mode = True
                voice_state.last_lumi_activity = time.time()
            # Extrait la question après "Lumi"
            clean = tl
            for w in _WAKE:
                clean = clean.replace(w, "")
            clean = clean.strip(" .,?!")
            if clean and len(clean) > 3 and _on_lumi_question:
                _on_lumi_question(text)
            else:
                play_tts("Oui, je t'écoute !")
            return

        # Mode Lumi actif → répond à tout
        with voice_state.lock:
            active = voice_state.lumi_mode
        if active and _on_lumi_question:
            with voice_state.lock:
                voice_state.last_lumi_activity = time.time()
            _on_lumi_question(text)

        # Log transcription passive
        with voice_state.lock:
            voice_state.transcript_log.append({
                "time": time.strftime("%H:%M:%S"),
                "text": text,
            })

    except Exception as e:
        with voice_state.lock:
            voice_state.last_transcript = f"[Erreur transcription: {e}]"
        print(f"[VOICE ERROR] {e}", flush=True)

def set_session_theme(theme: str):
    with voice_state.lock:
        voice_state.session_theme = theme

def get_status() -> dict:
    with voice_state.lock:
        return {
            "running":           voice_state.running,
            "is_recording":      voice_state.is_recording,
            "is_speaking":       voice_state.is_speaking,
            "last_transcript":   voice_state.last_transcript,
            "lumi_mode":         voice_state.lumi_mode,
            "session_theme":     voice_state.session_theme,
            "alert":             voice_state.alert,
            "transcript_log":    list(voice_state.transcript_log[-10:]),
            "last_theme":        "",
            "is_on_topic":       True,
            "last_lumi_activity": voice_state.last_lumi_activity,
        }

_play_tts = play_tts