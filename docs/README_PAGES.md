# LUMI — Documentation des pages

<div align="center">

```
  ●  LUMI  —  Documentation technique
```

*Master SISE 2025–2026*
**Aya Mecheri · Maissa Lajimi · Mazilda Zehraoui**

</div>

---

## Table des matières

1. [app.py — Routing principal](#1-apppy--routing-principal)
2. [auth.py — Authentification](#2-authpy--authentification)
3. [home.py — Accueil](#3-homepy--accueil)
4. [session.py — Session d'étude](#4-sessionpy--session-détude)
5. [analytics.py — Analytiques](#5-analyticspy--analytiques)
6. [Services](#6-services)

---

## 1. `app.py` — Routing principal

### Rôle
Point d'entrée de l'application. Gère la navigation entre les pages via `st.session_state["page"]`.

### Flux de navigation

```
Démarrage
    │
    ▼
┌───────────┐     non connecté     ┌──────────┐
│  app.py   │ ──────────────────▶  │  auth    │
└───────────┘                      └──────────┘
    │                                   │
    │         connecté                  │ login OK
    ▼                                   ▼
┌──────────┐   nouvelle session   ┌──────────┐
│   home   │ ──────────────────▶  │ session  │
└──────────┘                      └──────────┘
    │                                   │
    │       voir analytics              │ quitter
    ▼                                   ▼
┌──────────┐                       ┌──────────┐
│analytics │                       │   home   │
└──────────┘                       └──────────┘
```

### Variables de routing

| Variable | Valeurs | Description |
|---|---|---|
| `st.session_state["page"]` | `"home"`, `"session"`, `"analytics"` | Page active |
| `st.session_state["user_id"]` | entier | ID utilisateur connecté |
| `st.session_state["username"]` | string | Nom d'utilisateur |

---

## 2. `auth.py` — Authentification

### Rôle
Page de connexion et d'inscription. Premier écran affiché si l'utilisateur n'est pas connecté.

### Interface

```
┌─────────────────────────────────┐
│                                 │
│         ●  Lumi                 │
│   Ton assistant d'étude         │
│                                 │
│  ┌─────────────────────────┐   │
│  │  Connexion │ Inscription │   │
│  └─────────────────────────┘   │
│                                 │
│  Nom d'utilisateur              │
│  ┌─────────────────────────┐   │
│  │                         │   │
│  └─────────────────────────┘   │
│                                 │
│  Mot de passe                   │
│  ┌─────────────────────────┐   │
│  │                         │   │
│  └─────────────────────────┘   │
│                                 │
│  [ Se connecter ]               │
│                                 │
└─────────────────────────────────┘
```

### Logique

- **Connexion** : appel `login_user(username, password)` → hash bcrypt → retourne `user_id` ou `None`
- **Inscription** : validation (champs vides, passwords identiques, min 6 chars) → `create_user()` → switch vers onglet connexion
- **Sécurité** : mots de passe hashés avec `bcrypt.hashpw()`, jamais stockés en clair

### Fonctions appelées

```python
login_user(username: str, password: str) -> dict | None
create_user(username: str, password: str) -> bool
```

---

## 3. `home.py` — Accueil

### Rôle
Page d'accueil après connexion. Permet de créer une nouvelle session et de consulter l'historique.

### Interface

```
┌──────────────────────────────────────────────┐
│  ●  Lumi                    [ Se déconnecter]│
│                                              │
│  Bonne journée, [username] !                 │
│  Prêt à étudier ?                            │
│                                              │
│  ┌──────────────────────┐                   │
│  │  Titre de la session │                   │
│  └──────────────────────┘                   │
│  [ Commencer une session ]                   │
│                                              │
│  ── Sessions récentes ─────────────────────  │
│                                              │
│  ┌────────────────┐  ┌────────────────┐     │
│  │ Session 1      │  │ Session 2      │     │
│  │ Score: 87%     │  │ Score: 72%     │     │
│  │ 45 min         │  │ 30 min         │     │
│  │ [Analytics]    │  │ [Analytics]    │     │
│  └────────────────┘  └────────────────┘     │
└──────────────────────────────────────────────┘
```

### Fonctions appelées

```python
get_sessions(user_id: int) -> list[dict]
create_session(title: str) -> int   # retourne session_id
```

---

## 4. `session.py` — Session d'étude

### Rôle
Page principale de l'application. Orchestre la caméra, le micro, le chat et les onglets de contenu.

### Interface complète

```
┌──────────────────────────────────────────────────────┐
│  ● Lumi      [  12:34  ]              [ Quitter ]    │
│  ────────────────────────────────────────────────    │
│                                                      │
│  ┌────────────┐  ┌───────────────────────────────┐  │
│  │ SOURCES    │  │  CAMÉRA        │  SCORES       │  │
│  │ ☐ cours.pdf│  │                │  Global  87%  │  │
│  │            │  │   [ visage ]   │  Caméra  91%  │  │
│  │ AJOUTER    │  │                │  EAR    0.34  │  │
│  │ [upload]   │  │ [▶ Commencer] │               │  │
│  └────────────┘  └───────────────────────────────┘  │
│                                                      │
│  ┌─ Diagnostics voix ──────────────────────────┐    │
│  │  Loop:ON  Enreg:OUI  Lumi:NON  Parle:NON    │    │
│  │  "lumi c'est quoi le machine learning"       │    │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  [ Sources ]        [ Lumi ]        [ Résumé ]       │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### États de la session

```
Session créée
    │
    ▼
┌──────────────┐   upload source   ┌──────────────┐
│  Gate upload │ ────────────────▶ │  Prêt        │
│  (logo pulse)│                   │  Micro ON    │
└──────────────┘                   └──────────────┘
                                         │
                                         │  clic "Commencer"
                                         ▼
                                   ┌──────────────┐
                                   │  Session     │
                                   │  active      │
                                   │  Timer ON    │
                                   │  Polling ON  │
                                   └──────────────┘
```

### Composants techniques

#### Timer
```python
# st.components.v1.html() — iframe isolé, persiste entre reruns
components.html(f"""
<div id="t">00:00</div>
<script>
var s0 = {start_ts};
setInterval(() => {{ ... }}, 1000);
</script>
""", height=40)
```

#### Voice Pipeline
```
Microphone
    │  sounddevice (chunks 6s)
    ▼
RMS check (seuil 0.001)
    │  bruit filtré
    ▼
Whisper v3 API
    │  language="fr", prompt="Lumi, Loumi..."
    ▼
Wake word detection
    │  ["lumi", "loumi", "lumie", ...]
    ▼
lumi_mode = True
    │
    ▼
Groq LLM (Llama 3.1-8b)
    │
    ▼
gTTS → playsound
```

#### Score de concentration
```
Caméra (MediaPipe)
    ├── EAR (Eye Aspect Ratio)     → somnolence
    ├── MAR (Mouth Aspect Ratio)   → bâillements (seuil 0.25)
    ├── Yaw / Pitch                → orientation tête
    └── Score caméra (0-100)
            │
            ▼
    Concentration Engine
            ├── Score caméra  (pondération 60%)
            ├── Score curseur (pondération 20%)
            └── Visibilité onglet (pondération 20%)
                    │
                    ▼
            Score Global (0-100)
```

### Onglets

#### Onglet Sources
- Affichage des PDFs uploadés en cards
- Ouverture d'une source → iframe PDF + zone notes
- Notes corrigées automatiquement par Groq (`_groq_clean_note`)

#### Onglet Lumi (Chat)
- Résumé automatique au chargement (2 phrases, Llama 3.1)
- Bulles alignées : user à droite (violet), Lumi à gauche (sombre)
- Polling toutes les 5s pour détecter les nouveaux messages vocaux
- Input texte + bouton "Envoyer"

#### Onglet Résumé
- Résumé LLM généré automatiquement
- Bouton "Télécharger le résumé (PDF)" — export fpdf2 stylé

### Snapshot timeline (toutes les 30s)
```python
add_timeline_point(sid, elapsed,
    score_global, score_camera, score_behavior,
    ear, yaw, pitch, lumi_mode)
```

---

## 5. `analytics.py` — Analytiques

### Rôle
Rapport complet d'une session terminée. Généré par LLM, visualisé en HTML.

### Interface

```
┌──────────────────────────────────────────────┐
│  ← Retour         Rapport — [Titre session]  │
│                                              │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────┐│
│  │  87%   │  │  45min │  │   12   │  │  3 ││
│  │ Score  │  │ Durée  │  │ Msgs   │  │ ↑  ││
│  └────────┘  └────────┘  └────────┘  └────┘│
│                                              │
│  Timeline de concentration                   │
│  ████████░░████████████░░░████████           │
│                                              │
│  ── Analyse LLM ──────────────────────────   │
│  Points forts · Points faibles               │
│  Recommandations · Évaluation globale        │
│                                              │
│  ── Alertes caméra ───────────────────────   │
│  Somnolence · Bâillement · Distraction       │
└──────────────────────────────────────────────┘
```

### Rapport LLM (JSON structuré)
```json
{
  "points_forts": "...",
  "points_faibles": "...",
  "recommandations": "...",
  "evaluation_globale": "...",
  "score_estime": 85
}
```

### KPIs affichés

| KPI | Source |
|---|---|
| Score moyen | `AVG(score_global)` sur timeline |
| Durée session | `session.duration_sec` |
| Messages Lumi | `COUNT(chat_messages)` |
| Appels Lumi | `session_stats.lumi_call` |

---

## 6. Services

### `vision.py` — Détection faciale

```python
# Seuils de détection
EAR_THRESHOLD  = 0.25   # En dessous → yeux fermés
YAWN_THRESHOLD = 0.25   # MAR > seuil → bâillement
YAWN_DURATION  = 0.8    # secondes de bâillement continu

# Alertes TTS (bloquées si lumi_mode actif)
_play_alert("Tu sembles fatigué, pense à faire une pause !")
```

**Landmarks MediaPipe utilisés :**
- Points 33, 133, 160, 144, 158, 153 → EAR gauche
- Points 362, 263, 385, 380, 387, 373 → EAR droite
- Points 13, 14, 78, 308 → MAR (bâillement)

---

### `voice_detector.py` — Assistant vocal

```
Wake words supportés :
"lumi" · "loumi" · "loumy" · "lumy" · "lumie"
"lomy" · "loomy" · "hey lumi" · "hé lumi"

Paramètres audio :
  Samplerate   : 16 000 Hz
  Channels     : 1 (mono)
  Chunk        : 6 secondes
  RMS minimum  : 0.001
  Language     : fr (Whisper)
```

**Timeout inactivité (30s) :**
> *"Bon je vais dormir un peu, dis Lumi quand t'auras besoin de moi !"*

**Commande de fin :**
> Dire "merci Lumi" → `lumi_mode = False`

---

### `concentration_engine.py` — Score global

```python
score_final = (
    score_camera   * 0.60 +
    score_cursor   * 0.20 +
    score_tab      * 0.20
)
```

---

### `cursor_tracker.py` — Suivi comportemental

Injecte du JavaScript dans la page Streamlit pour détecter :
- Inactivité souris (> 60s → pénalité)
- Changement d'onglet navigateur (→ pénalité)

---

## ✦ Variables `st.session_state` principales

| Clé | Type | Description |
|---|---|---|
| `page` | str | Page active |
| `user_id` | int | ID utilisateur |
| `session_id` | int | ID session courante |
| `session_ready` | bool | Session démarrée |
| `session_start` | float | `time.time()` au démarrage |
| `voice_started` | bool | Thread micro actif |
| `summary_done` | bool | Résumé initial généré |
| `_last_msg_count` | int | Détection nouveaux messages |

---

<div align="center">
<sub>● LUMI · Master SISE 2025–2026 · Aya Mecheri · Maissa Lajimi · Mazilda Zehraoui</sub>
</div>
