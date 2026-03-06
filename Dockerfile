# ── Base image ────────────────────────────────────────────────
FROM python:3.10-slim

# ── Métadonnées ───────────────────────────────────────────────
LABEL maintainer="Aya Mecheri, Maissa Lajimi, Mazilda Zehraoui"
LABEL description="Lumi — Assistant d'étude intelligent"

# ── Variables d'environnement ─────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# ── Dépendances système ───────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgomp1 \
    libsndfile1 \
    ffmpeg \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Utilisateur non-root (obligatoire Hugging Face) ──────────
RUN useradd -m -u 1000 user
USER user

# ── Répertoire de travail ─────────────────────────────────────
WORKDIR /home/user/app

# ── Dépendances Python ────────────────────────────────────────
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Code source ───────────────────────────────────────────────
COPY --chown=user . .

# ── Dossier pour la DB ────────────────────────────────────────
RUN mkdir -p /home/user/app/data

# ── Config Streamlit ──────────────────────────────────────────
RUN mkdir -p /home/user/.streamlit
COPY --chown=user .streamlit/config.toml /home/user/.streamlit/config.toml

# ── Port Hugging Face (obligatoire : 7860) ────────────────────
EXPOSE 7860

# ── Démarrage ─────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
