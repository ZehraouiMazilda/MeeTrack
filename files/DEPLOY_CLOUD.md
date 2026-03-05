# ☁️ Déployer FocusMeet sur le cloud (HTTPS + multi-machines)

## Stack
- **Streamlit Community Cloud** → hébergement gratuit, HTTPS auto, webcam ✅
- **Upstash Redis** → base partagée entre tous les participants, gratuit ✅

---

## Étape 1 — Créer une base Redis gratuite (Upstash)

1. Aller sur https://upstash.com → "Sign up" (gratuit)
2. Créer une base : **New Database** → choisir région Europe → créer
3. Dans le dashboard, copier :
   - **REST URL** (ex: `https://eu1-xxx.upstash.io`)
   - **REST Token** (ex: `AXXXXXXXxxx...`)

---

## Étape 2 — Mettre le code sur GitHub

Structure du repo :
```
focusmeet/
├── app.py
├── requirements.txt
└── .streamlit/
    └── config.toml
```

```bash
git init && git add .
git commit -m "FocusMeet"
git remote add origin https://github.com/TON_USERNAME/focusmeet.git
git push -u origin main
```

---

## Étape 3 — Déployer sur Streamlit Community Cloud

1. Aller sur https://share.streamlit.io → se connecter avec GitHub
2. **New app** → choisir votre repo → `app.py` → **Deploy**
3. Dans **Settings → Secrets**, ajouter :

```toml
REDIS_URL = "https://eu1-xxx.upstash.io"
REDIS_TOKEN = "AXXXXXXXxxx..."
```

4. **Save** → l'app redémarre automatiquement

---

## Étape 4 — Utiliser

- Partager l'URL Streamlit (ex: `https://focusmeet.streamlit.app`)
- Chaque personne ouvre l'URL sur **sa propre machine**
- Une personne crée une room → partage le **code à 6 caractères**
- Les autres entrent le code → tout le monde voit les scores en temps réel ✅

---

## Sans Redis (mode local / LAN)

Si `REDIS_URL` n'est pas défini, l'app utilise la mémoire locale.
Cela fonctionne si tout le monde se connecte au **même serveur** :

```bash
streamlit run app.py --server.address 0.0.0.0
```
