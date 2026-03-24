"""Configuration gunicorn pour Papy Babou Podcast.

Résout deux problèmes en production (Replit) :
1. Un seul worker sync bloque le serveur pendant les productions longues
   → Utilise gthread (threads) pour permettre le polling du dashboard
2. Timeout trop court (30s par défaut) tue les workers pendant la production
   → Timeout élevé car les jobs longs tournent en subprocess, pas dans le worker

Usage :
    gunicorn -c gunicorn.conf.py web:app
"""

import multiprocessing
import os

# ── Binding ──────────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
reuse_port = True

# ── Workers ──────────────────────────────────────────────────────────────────
# gthread : chaque worker a N threads, ce qui permet de servir les requêtes
# de polling du dashboard pendant qu'un thread attend un subprocess de production.
worker_class = "gthread"

# IMPORTANT : 1 seul worker car l'état des jobs (_jobs dict) est en mémoire.
# Avec 2+ workers (= processus séparés), un job créé dans le worker A
# est introuvable par le worker B → "Job introuvable" sur le polling.
# La concurrence est assurée par les threads (4 threads = 4 requêtes simultanées).
workers = int(os.getenv("GUNICORN_WORKERS", "1"))

# Threads par worker : permet de gérer le polling concurrent pendant
# qu'un thread attend un subprocess de production (proc.communicate).
# 8 threads = 8 requêtes simultanées. Même si 2 productions longues bloquent
# 2 threads, il reste 6 threads pour le dashboard/polling/validation.
threads = int(os.getenv("GUNICORN_THREADS", "8"))

# ── Timeouts ─────────────────────────────────────────────────────────────────
# Timeout élevé : les productions longues tournent en subprocess (via _run_cli),
# mais le thread qui fait proc.communicate() bloque pendant la durée du timeout
# du subprocess (jusqu'à 30min). Le worker ne doit pas être tué pendant ce temps.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "7500"))  # 2h05 (doit être > _TIMEOUT_PRODUIRE + marge)

# Graceful timeout pour laisser les subprocesses finir proprement.
graceful_timeout = 60

# Keep-alive pour les connexions HTTP persistantes (polling).
keepalive = 5

# ── Logging ──────────────────────────────────────────────────────────────────
accesslog = "-"      # stdout
errorlog = "-"       # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# ── Hooks ────────────────────────────────────────────────────────────────────
def post_fork(server, worker):
    """Après fork : réinitialiser le pool PostgreSQL dans chaque worker.

    Le pool psycopg2 n'est pas fork-safe — chaque worker doit avoir son propre pool.
    """
    try:
        import database
        database.close_pool()
    except Exception:
        pass


def worker_exit(server, worker):
    """Quand le worker meurt : envoyer SIGTERM aux subprocesses de production.

    Sans cela, quand Replit recycle le container :
    1. SIGTERM → gunicorn master → workers meurent
    2. Subprocesses main.py deviennent orphelins → SIGKILL → aucun checkpoint sauvé
    Ce hook garantit que les subprocesses reçoivent SIGTERM et peuvent sauvegarder.
    """
    try:
        import web
        web._terminate_all_subprocesses()
    except Exception:
        pass
