"""Authentification par mot de passe (back-office Django).

Le téléphone n'est unique que parmi les comptes particuliers et l'équipe : le
back-office n'accepte donc que ces comptes-là. Les comptes professionnels
passent par email + mot de passe + code SMS (services.pro_login).
"""
from django.contrib.auth.backends import ModelBackend

from .models import User, normalize_phone


class PhonePasswordBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        raw = username if username is not None else kwargs.get(User.USERNAME_FIELD)
        try:
            phone = normalize_phone(raw or "")
        except Exception:
            return None
        user = User.objects.filter(phone=phone).exclude(role__in=User.PRO_ROLES).first()
        if user is None:
            User().set_password(password)  # même durée de réponse qu'un compte existant
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
