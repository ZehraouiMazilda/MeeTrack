# 🎯 FocusMeet — Real-time Meeting Concentration Tracker

Détection de concentration en temps réel via webcam pour vos réunions.

---

## 🚀 Installation rapide

### Option A — Python local

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Option B — Docker (recommandé)

```bash
docker build -t focusmeet .
docker run -p 8501:8501 focusmeet
```

Ouvrez ensuite http://localhost:8501 dans votre navigateur.

> ⚠️ La webcam doit être accessible depuis le navigateur (HTTPS ou localhost).

---

## 📖 Utilisation

1. **Rejoindre** : cliquez sur "Add / Join as participant", entrez votre prénom, cliquez **Join**.
2. **Activer la webcam** : cliquez sur **START** dans le widget vidéo de votre case.
3. **Analyser** : la barre latérale (sidebar) se met à jour en temps réel avec votre score de concentration.
4. **Déplier les détails** : cliquez sur "📈 Prénom — Details" dans la sidebar pour voir EAR, yaw, pitch, blink rate.
5. **Ajouter d'autres participants** : répétez l'étape 1 depuis d'autres onglets/machines.

---

## 🧠 Comment ça marche ?

Le score (0–100%) combine 3 signaux analysés via **MediaPipe Face Mesh** :

| Signal | Poids | Description |
|--------|-------|-------------|
| **Eye Aspect Ratio (EAR)** | 40% | Détecte la somnolence / yeux fermés |
| **Head Pose (Yaw + Pitch)** | 40% | Détecte si le visage est tourné / tête baissée |
| **Blink rate** | 20% | Fréquence de clignements (norme : 10–20/min) |

**Interprétation :**
- 🟢 70–100% → Concentré
- 🟡 40–69% → Distrait
- 🔴 0–39%  → Absent / non présent

---

## 📦 Stack technique

- **Streamlit** — interface web
- **streamlit-webrtc** — flux vidéo temps réel (WebRTC)
- **MediaPipe** — détection de visage et landmarks
- **OpenCV** — traitement d'image
- **NumPy** — calcul des scores

---

## 🗂️ Structure

```
focus_meeting/
├── app.py           # Application principale
├── requirements.txt
├── Dockerfile
└── README.md
```
