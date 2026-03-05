import os
from dotenv import load_dotenv

load_dotenv()

def _get_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def _ask(prompt: str, system: str = "", max_tokens: int = 1500) -> str:
    client = _get_client()
    msgs = [{"role": "user", "content": prompt}]
    kwargs = {"model": "claude-haiku-4-5-20251001", "max_tokens": max_tokens, "messages": msgs}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text


def generate_summary(transcript: list, participants: list, meeting_name: str, duration_sec: float) -> dict:
    if not transcript:
        return {
            "summary": "Aucune transcription disponible.",
            "key_points": [],
            "decisions": [],
            "tasks": "[]",
            "themes": "[]"
        }

    transcript_text = "\n".join(
        f"[{e['timestamp']}] {e['username']}: {e['text']}"
        for e in transcript
    )
    participant_names = ", ".join(p["username"] for p in participants)
    mins = int(duration_sec // 60)

    prompt = f"""Voici la transcription d'une réunion intitulée "{meeting_name}".
Durée : {mins} minutes. Participants : {participant_names}.

TRANSCRIPTION :
{transcript_text}

Génère une analyse structurée en JSON avec exactement ces clés :
{{
  "summary": "Résumé exécutif en 3-4 phrases",
  "key_points": ["point 1", "point 2", "point 3"],
  "decisions": ["décision 1", "décision 2"],
  "tasks": [
    {{"task": "description", "owner": "nom ou Equipe", "deadline": "date ou Non definie"}}
  ],
  "themes": ["thème 1", "thème 2", "thème 3"]
}}

Réponds UNIQUEMENT avec le JSON, sans markdown ni texte avant/après."""

    import json
    try:
        raw = _ask(prompt, max_tokens=1500)
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return {
            "summary": data.get("summary", ""),
            "key_points": data.get("key_points", []),
            "decisions": data.get("decisions", []),
            "tasks": json.dumps(data.get("tasks", []), ensure_ascii=False),
            "themes": json.dumps(data.get("themes", []), ensure_ascii=False),
        }
    except Exception as e:
        return {
            "summary": f"Erreur lors de la génération : {e}",
            "key_points": [],
            "decisions": [],
            "tasks": "[]",
            "themes": "[]"
        }


def get_participant_themes(transcript: list, username: str) -> list:
    user_lines = [e for e in transcript if e.get("username") == username]
    if not user_lines:
        return []
    text = "\n".join(f"- {e['text']}" for e in user_lines)
    prompt = f"""Voici ce qu'a dit {username} pendant la réunion :
{text}

Identifie les 3 principaux thèmes abordés par cette personne.
Réponds avec un JSON : {{"themes": ["thème 1", "thème 2", "thème 3"]}}
Réponds UNIQUEMENT avec le JSON."""
    import json
    try:
        raw = _ask(prompt, max_tokens=300)
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw).get("themes", [])
    except:
        return []


def chatbot_response(history: list, user_message: str, meeting_context: str) -> str:
    client = _get_client()
    system = f"""Tu es un assistant intelligent qui aide à analyser une réunion.
Contexte de la réunion :
{meeting_context}

Tu réponds en français, de manière concise et utile."""
    messages = history + [{"role": "user", "content": user_message}]
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system,
            messages=messages
        )
        return resp.content[0].text
    except Exception as e:
        return f"Erreur : {e}"