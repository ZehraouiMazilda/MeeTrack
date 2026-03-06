import sqlite3
import json
import bcrypt
import os
from datetime import datetime

import os
DB_PATH = os.environ.get("DB_PATH", "lumi.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        username     TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at   TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        title        TEXT NOT NULL,
        theme        TEXT DEFAULT '',
        duration_sec REAL DEFAULT 0,
        created_at   TEXT DEFAULT (datetime('now')),
        updated_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sources (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        filename   TEXT NOT NULL,
        content    TEXT DEFAULT '',
        added_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        source_id  INTEGER,
        raw_text   TEXT NOT NULL,
        clean_text TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id),
        FOREIGN KEY (source_id)  REFERENCES sources(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        role       TEXT NOT NULL,
        content    TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS voice_transcripts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER NOT NULL,
        text         TEXT NOT NULL,
        lang         TEXT DEFAULT 'fr',
        theme        TEXT DEFAULT '',
        on_topic     INTEGER DEFAULT 1,
        mode         TEXT DEFAULT 'passive',
        created_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS distraction_events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER NOT NULL,
        event_type   TEXT NOT NULL,
        detail       TEXT DEFAULT '',
        created_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    # Timeline concentration (snapshot toutes les 30s)
    c.execute("""
    CREATE TABLE IF NOT EXISTS concentration_timeline (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      INTEGER NOT NULL,
        elapsed_sec     REAL NOT NULL,
        score_global    INTEGER,
        score_camera    INTEGER,
        score_behavior  INTEGER,
        ear             REAL,
        yaw             REAL,
        pitch           REAL,
        lumi_mode       INTEGER DEFAULT 0,
        created_at      TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    # Stats résumé session (mise à jour au Quitter)
    c.execute("""
    CREATE TABLE IF NOT EXISTS session_stats (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id          INTEGER UNIQUE NOT NULL,
        score_avg           REAL DEFAULT 0,
        score_min           INTEGER DEFAULT 0,
        score_max           INTEGER DEFAULT 100,
        alert_eyes          INTEGER DEFAULT 0,
        alert_yaw           INTEGER DEFAULT 0,
        alert_pitch         INTEGER DEFAULT 0,
        alert_no_face       INTEGER DEFAULT 0,
        lumi_calls          INTEGER DEFAULT 0,
        sources_count       INTEGER DEFAULT 0,
        notes_count         INTEGER DEFAULT 0,
        summary             TEXT DEFAULT '',
        started_at          TEXT DEFAULT (datetime('now')),
        ended_at            TEXT DEFAULT '',
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")

    conn.commit()
    conn.close()

# ── Users ──────────────────────────────────────────────────────
def create_user(username, password):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_conn()
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?,?)", (username, hashed))
        conn.commit(); conn.close()
        return True, "Compte créé !"
    except sqlite3.IntegrityError:
        return False, "Nom d'utilisateur déjà pris."

def login_user(username, password):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return True, dict(row)
    return False, None

# ── Sessions ───────────────────────────────────────────────────
def create_session(title, user_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sessions (title, user_id) VALUES (?,?)", (title, user_id))
    sid = cur.lastrowid
    conn.commit(); conn.close()
    return sid

def update_session(session_id, theme=None, duration_sec=None):
    conn = get_conn()
    if theme is not None:
        conn.execute("UPDATE sessions SET theme=?, updated_at=datetime('now') WHERE id=?", (theme, session_id))
    if duration_sec is not None:
        conn.execute("UPDATE sessions SET duration_sec=?, updated_at=datetime('now') WHERE id=?", (duration_sec, session_id))
    conn.commit(); conn.close()

def get_all_sessions(user_id=None):
    conn = get_conn()
    if user_id:
        rows = conn.execute("SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_session(session_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── Sources ────────────────────────────────────────────────────
def add_source(session_id, filename, content=""):
    conn = get_conn()
    cur = conn.execute("INSERT INTO sources (session_id, filename, content) VALUES (?,?,?)",
                       (session_id, filename, content))
    sid = cur.lastrowid
    conn.commit(); conn.close()
    return sid

def get_sources(session_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sources WHERE session_id=? ORDER BY added_at", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_source(source_id):
    conn = get_conn()
    conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
    conn.execute("DELETE FROM notes WHERE source_id=?", (source_id,))
    conn.commit(); conn.close()

# ── Notes ──────────────────────────────────────────────────────
def add_note(session_id, raw_text, clean_text, source_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO notes (session_id, source_id, raw_text, clean_text) VALUES (?,?,?,?)",
        (session_id, source_id, raw_text, clean_text))
    nid = cur.lastrowid
    conn.commit(); conn.close()
    return nid

def get_notes(session_id, source_id=None):
    conn = get_conn()
    if source_id:
        rows = conn.execute("SELECT * FROM notes WHERE session_id=? AND source_id=? ORDER BY created_at",
                            (session_id, source_id)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM notes WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_note(note_id):
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit(); conn.close()

# ── Chat ───────────────────────────────────────────────────────
def add_chat_message(session_id, role, content):
    conn = get_conn()
    conn.execute("INSERT INTO chat_messages (session_id, role, content) VALUES (?,?,?)",
                 (session_id, role, content))
    conn.commit(); conn.close()

def get_chat_messages(session_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Voice transcripts ──────────────────────────────────────────
def add_transcript(session_id, text, lang="fr", theme="", on_topic=True, mode="passive"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO voice_transcripts (session_id, text, lang, theme, on_topic, mode) VALUES (?,?,?,?,?,?)",
        (session_id, text, lang, theme, int(on_topic), mode))
    conn.commit(); conn.close()

def get_transcripts(session_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM voice_transcripts WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Distraction events ─────────────────────────────────────────
def add_distraction(session_id, event_type, detail=""):
    conn = get_conn()
    conn.execute("INSERT INTO distraction_events (session_id, event_type, detail) VALUES (?,?,?)",
                 (session_id, event_type, detail))
    conn.commit(); conn.close()

def get_distractions(session_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM distraction_events WHERE session_id=? ORDER BY created_at", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Concentration timeline ─────────────────────────────────────
def add_timeline_point(session_id, elapsed_sec, score_global, score_camera=0,
                       score_behavior=0, ear=0.0, yaw=0.0, pitch=0.0, lumi_mode=False):
    conn = get_conn()
    conn.execute("""
        INSERT INTO concentration_timeline
        (session_id, elapsed_sec, score_global, score_camera, score_behavior, ear, yaw, pitch, lumi_mode)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, elapsed_sec, score_global, score_camera, score_behavior,
         round(ear,3), round(yaw,1), round(pitch,1), int(lumi_mode)))
    conn.commit(); conn.close()

def get_timeline(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM concentration_timeline WHERE session_id=? ORDER BY elapsed_sec",
        (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Session stats ──────────────────────────────────────────────
def init_session_stats(session_id):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO session_stats (session_id) VALUES (?)""", (session_id,))
    conn.commit(); conn.close()

def increment_alert_stat(session_id, alert_type):
    """alert_type: eyes | yaw | pitch | no_face | lumi_call"""
    col_map = {
        "eyes": "alert_eyes", "yaw": "alert_yaw",
        "pitch": "alert_pitch", "no_face": "alert_no_face",
        "lumi_call": "lumi_calls"
    }
    col = col_map.get(alert_type)
    if not col:
        return
    conn = get_conn()
    conn.execute(f"UPDATE session_stats SET {col}={col}+1 WHERE session_id=?", (session_id,))
    conn.commit(); conn.close()

def finalize_session_stats(session_id, summary=""):
    """Appelé au Quitter — calcule avg/min/max depuis la timeline."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT score_global FROM concentration_timeline WHERE session_id=?",
        (session_id,)).fetchall()
    scores = [r["score_global"] for r in rows if r["score_global"] is not None]

    avg = round(sum(scores)/len(scores), 1) if scores else 0
    mn  = min(scores) if scores else 0
    mx  = max(scores) if scores else 100

    sources_count = conn.execute(
        "SELECT COUNT(*) FROM sources WHERE session_id=?", (session_id,)).fetchone()[0]
    notes_count = conn.execute(
        "SELECT COUNT(*) FROM notes WHERE session_id=?", (session_id,)).fetchone()[0]

    conn.execute("""
        UPDATE session_stats SET
            score_avg=?, score_min=?, score_max=?,
            sources_count=?, notes_count=?,
            summary=?, ended_at=datetime('now')
        WHERE session_id=?""",
        (avg, mn, mx, sources_count, notes_count, summary, session_id))
    conn.commit(); conn.close()

def get_session_stats(session_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM session_stats WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}

def get_all_session_stats(user_id=None):
    """Pour la home — toutes les sessions avec stats résumées."""
    conn = get_conn()
    query = """
        SELECT s.id, s.title, s.theme, s.duration_sec, s.created_at,
               ss.score_avg, ss.score_min, ss.score_max,
               ss.alert_eyes, ss.alert_yaw, ss.alert_pitch, ss.alert_no_face,
               ss.lumi_calls, ss.sources_count, ss.notes_count, ss.summary
        FROM sessions s
        LEFT JOIN session_stats ss ON s.id = ss.session_id
        ORDER BY s.created_at DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(r) for r in rows]