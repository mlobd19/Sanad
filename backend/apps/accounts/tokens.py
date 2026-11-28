"""Connexions à l'app : un jeton par appareil, à durée de vie limitée, révocable.

- Particulier : 30 jours ; compte professionnel (agent assureur, membre d'entreprise) : 8 h.
- Seule l'empreinte SHA-256 est enregistrée (models.AuthToken) ; le jeton n'est montré qu'une fois.
- Jeton expiré ou révoqué → 401 : l'app renvoie vers /connexion (lib/spaces.ts).
- En-tête inchangé pour l'app : « Authorization: Token <jeton> ».
- Particulier : le jeton seul n'ouvre rien ; il faut une session ouverte par le code PIN (accounts/pin.py).
  Sinon 403 « pin_required » (code à saisir) ou « pin_setup » (code à choisir après le SMS), sauf pour
  les vues marquées `pin_exempt` (code PIN, déconnexion) ; une vue publique (AllowAny) le traite en visiteur.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import AllowAny

from . import pin
from .models import AuthToken, User

KEYWORD = "Token"
LAST_USED_PRECISION = timedelta(minutes=5)  # évite une écriture en base à chaque requête


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def lifetime(user: User) -> timedelta:
    if user.is_pro or user.role == User.Role.STAFF:
        return timedelta(hours=settings.AUTH_TOKEN_TTL_PRO_HOURS)
    return timedelta(days=settings.AUTH_TOKEN_TTL_CUSTOMER_DAYS)


def issue_token(user: User, request=None) -> str:
    """Nouvelle connexion pour cet appareil (jamais un jeton partagé entre téléphones).

    Particulier (après le code SMS) : l'appareil doit d'abord choisir le code PIN du compte.
    """
    key = secrets.token_urlsafe(32)
    agent = (request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:200]
    now = timezone.now()
    AuthToken.objects.create(user=user, digest=digest(key), expires_at=now + lifetime(user), user_agent=agent,
                             pin_setup_until=now + pin.SETUP_WINDOW if pin.applies(user) else None)
    return key


def revoke_others(user: User, keep: AuthToken | None) -> int:
    """« Déconnecter mes autres appareils » : ferme toutes les connexions sauf celle en cours."""
    qs = AuthToken.objects.filter(user=user)
    if keep is not None:
        qs = qs.exclude(pk=keep.pk)
    return qs.delete()[0]


def purge_expired() -> int:
    """Supprime les connexions expirées (tâche quotidienne et commande purge_expired_tokens)."""
    return AuthToken.objects.filter(expires_at__lte=timezone.now()).delete()[0]


class PinRequired(APIException):
    """Particulier sans session ouverte par le code PIN : l'app affiche l'écran du code (et garde le jeton)."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, code: str):
        message = "Choisissez votre code." if code == "pin_setup" else "Entrez votre code."
        super().__init__({"detail": message, "code": code})


class ExpiringTokenAuthentication(BaseAuthentication):
    """Authentification de l'API par jeton d'appareil à durée de vie limitée."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != KEYWORD.lower().encode():
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("En-tête d'authentification invalide.")
        try:
            key = parts[1].decode()
        except UnicodeError:
            raise AuthenticationFailed("En-tête d'authentification invalide.") from None

        token = AuthToken.objects.select_related("user").filter(digest=digest(key)).first()
        if token is None:
            raise AuthenticationFailed("Session fermée. Reconnectez-vous.")
        now = timezone.now()
        if token.expires_at <= now:
            token.delete()
            raise AuthenticationFailed("Session expirée. Reconnectez-vous.")
        if not token.user.is_active:
            raise AuthenticationFailed("Compte désactivé.")
        if pin.applies(token.user) and not self._pin_ok(request, token, now):
            return None  # vue publique : traitée comme pour un visiteur
        if token.last_used_at is None or now - token.last_used_at > LAST_USED_PRECISION:
            AuthToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user, token

    @staticmethod
    def _pin_ok(request, token: AuthToken, now) -> bool:
        """Session du code PIN : vrai si ouverte (ou vue du code PIN) ; faux pour une vue publique ; sinon 403."""
        current = pin.state(token, now)
        if current == "closed":  # aucun code PIN et plus de fenêtre de choix
            token.delete()
            raise AuthenticationFailed("Session fermée. Reconnectez-vous.")
        view = (getattr(request, "parser_context", None) or {}).get("view")
        if getattr(view, "pin_exempt", False):
            return True
        if current == "open":
            pin.touch(token)
            return True
        if any(permission is AllowAny for permission in getattr(view, "permission_classes", ())):
            return False
        raise PinRequired("pin_setup" if current == "setup" else "pin_required")

    def authenticate_header(self, request):
        return KEYWORD  # réponse 401 (et non 403) quand le jeton manque ou ne vaut plus rien
