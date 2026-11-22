"""Connexions à l'app : un jeton par appareil, à durée de vie limitée, révocable.

- Particulier : 30 jours ; compte professionnel (agent assureur, membre d'entreprise) : 8 h.
- Seule l'empreinte SHA-256 est enregistrée (models.AuthToken) ; le jeton n'est montré qu'une fois.
- Jeton expiré ou révoqué → 401 : l'app renvoie vers /connexion (lib/spaces.ts).
- En-tête inchangé pour l'app : « Authorization: Token <jeton> ».
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

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
    """Nouvelle connexion pour cet appareil (jamais un jeton partagé entre téléphones)."""
    key = secrets.token_urlsafe(32)
    agent = (request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:200]
    AuthToken.objects.create(user=user, digest=digest(key), expires_at=timezone.now() + lifetime(user),
                             user_agent=agent)
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
        if token.last_used_at is None or now - token.last_used_at > LAST_USED_PRECISION:
            AuthToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user, token

    def authenticate_header(self, request):
        return KEYWORD  # réponse 401 (et non 403) quand le jeton manque ou ne vaut plus rien
