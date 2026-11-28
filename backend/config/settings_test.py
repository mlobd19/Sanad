"""Réglages des tests : comme le développement local (DEBUG), sans mode démo ni valeurs du .env local.

Les tests qui en ont besoin activent DEMO_MODE eux-mêmes (fixture `settings`).
"""
import os

os.environ["DJANGO_DEBUG"] = "1"
os.environ["DEMO_MODE"] = "0"
os.environ["DEMO_PASSWORD"] = ""

from .settings import *  # noqa: E402,F403

# Hachage rapide des mots de passe et des codes PIN (le hacheur réel est lent par construction).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
