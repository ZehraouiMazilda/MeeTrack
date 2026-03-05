import sqlite3
import bcrypt
import random
import string
from datetime import datetime

DB_PATH = "meetrack.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            jitsi_url TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            ended_at TEXT,
            FOREIGN KEY (creator_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT DEFAULT (datetime('now')),
            left_at TEXT,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            language TEXT DEFAULT 'fr',
            timestamp TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (meeting_id) REFERENCES meetings(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS distraction_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            detail TEXT,
            timestamp TEXT DEFAULT (datetime('now')),
            duration_seconds REAL DEFAULT 0,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS speech_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            duration_seconds REAL NOT NULL,
            timestamp TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (meeting_id) REFERENCES meetings(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER UNIQUE NOT NULL,
            summary_text TEXT,
            tasks TEXT,
            themes TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        )
    """)

    conn.commit()
    conn.close()

# ── USERS ──────────────────────────────────────────────────────

def create_user(username: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_conn()
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
        conn.commit()
        conn.close()
        return True, "Compte créé avec succès !"
    except sqlite3.IntegrityError:
        return False, "Ce nom d'utilisateur existe déjà."

def login_user(username: str, password: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return True, dict(row)
    return False, None

def get_user_by_id(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── MEETINGS ───────────────────────────────────────────────────

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def create_meeting(name: str, creator_id: int):
    code = generate_code()
    # S'assure que le code est unique
    conn = get_conn()
    while conn.execute("SELECT id FROM meetings WHERE code = ?", (code,)).fetchone():
        code = generate_code()
    jitsi_url = f"https://meet.jit.si/meetrack-{code}"
    conn.execute(
        "INSERT INTO meetings (code, name, creator_id, jitsi_url) VALUES (?, ?, ?, ?)",
        (code, name, creator_id, jitsi_url)
    )
    conn.commit()
    meeting = conn.execute("SELECT * FROM meetings WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(meeting)

def get_meeting_by_code(code: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM meetings WHERE code = ?", (code.upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_meeting_by_id(meeting_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def end_meeting(meeting_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE meetings SET status = 'ended', ended_at = datetime('now') WHERE id = ?",
        (meeting_id,)
    )
    conn.commit()
    conn.close()

def get_user_meetings(user_id: int):
    """Retourne toutes les réunions créées par l'user ou auxquelles il a participé."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT m.*, u.username as creator_name
        FROM meetings m
        JOIN users u ON m.creator_id = u.id
        LEFT JOIN participants p ON m.id = p.meeting_id
        WHERE m.creator_id = ? OR p.user_id = ?
        ORDER BY m.created_at DESC
    """, (user_id, user_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── PARTICIPANTS ───────────────────────────────────────────────

def join_meeting(meeting_id: int, user_id: int):
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM participants WHERE meeting_id = ? AND user_id = ? AND left_at IS NULL",
        (meeting_id, user_id)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO participants (meeting_id, user_id) VALUES (?, ?)",
            (meeting_id, user_id)
        )
        conn.commit()
    conn.close()

def leave_meeting(meeting_id: int, user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE participants SET left_at = datetime('now') WHERE meeting_id = ? AND user_id = ? AND left_at IS NULL",
        (meeting_id, user_id)
    )
    conn.commit()
    conn.close()

def get_meeting_participants(meeting_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.id, u.username, p.joined_at, p.left_at
        FROM participants p
        JOIN users u ON p.user_id = u.id
        WHERE p.meeting_id = ?
        ORDER BY p.joined_at ASC
    """, (meeting_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── TRANSCRIPTS ────────────────────────────────────────────────

def add_transcript(meeting_id: int, user_id: int, text: str, language: str = "fr"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO transcripts (meeting_id, user_id, text, language) VALUES (?, ?, ?, ?)",
        (meeting_id, user_id, text, language)
    )
    conn.commit()
    conn.close()

def get_meeting_transcripts(meeting_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*, u.username
        FROM transcripts t
        JOIN users u ON t.user_id = u.id
        WHERE t.meeting_id = ?
        ORDER BY t.timestamp ASC
    """, (meeting_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── DISTRACTION EVENTS ─────────────────────────────────────────

def add_distraction_event(meeting_id: int, user_id: int, event_type: str, detail: str = "", duration: float = 0):
    conn = get_conn()
    conn.execute(
        "INSERT INTO distraction_events (meeting_id, user_id, type, detail, duration_seconds) VALUES (?, ?, ?, ?, ?)",
        (meeting_id, user_id, event_type, detail, duration)
    )
    conn.commit()
    conn.close()

def get_distraction_events(meeting_id: int, user_id: int = None):
    conn = get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM distraction_events WHERE meeting_id = ? AND user_id = ? ORDER BY timestamp ASC",
            (meeting_id, user_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM distraction_events WHERE meeting_id = ? ORDER BY timestamp ASC",
            (meeting_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── SPEECH SEGMENTS ────────────────────────────────────────────

def add_speech_segment(meeting_id: int, user_id: int, duration: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO speech_segments (meeting_id, user_id, duration_seconds) VALUES (?, ?, ?)",
        (meeting_id, user_id, duration)
    )
    conn.commit()
    conn.close()

def get_speech_times(meeting_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.username, SUM(s.duration_seconds) as total
        FROM speech_segments s
        JOIN users u ON s.user_id = u.id
        WHERE s.meeting_id = ?
        GROUP BY s.user_id
    """, (meeting_id,)).fetchall()
    conn.close()
    return {r["username"]: r["total"] for r in rows}

# ── SUMMARIES ──────────────────────────────────────────────────

def save_summary(meeting_id: int, summary_text: str, tasks: str, themes: str):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO summaries (meeting_id, summary_text, tasks, themes)
        VALUES (?, ?, ?, ?)
    """, (meeting_id, summary_text, tasks, themes))
    conn.commit()
    conn.close()

def get_summary(meeting_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM summaries WHERE meeting_id = ?", (meeting_id,)).fetchone()
    conn.close()
    return dict(row) if row else None