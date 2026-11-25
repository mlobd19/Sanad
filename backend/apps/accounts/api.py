from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import record

from . import services
from .models import IdentityCheck, User
from .services import LoginError, OtpError, OtpRateLimited, request_otp, verify_otp
from .tokens import issue_token, revoke_others



class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "full_name_ar", "nni", "language", "kyc_status", "role"]
        # Le nom d'un particulier vient de l'ANRPTS (eID) : seuls le NNI et la langue se modifient.
        read_only_fields = ["id", "phone", "email", "full_name", "full_name_ar", "kyc_status", "role"]


class CustomerOnly:
    """Mixin : vues réservées aux comptes particuliers."""

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.user.is_pro:
            self.permission_denied(request, message="Réservé aux comptes particuliers.")


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            request_otp(request.data.get("phone", ""))
        except OtpRateLimited as exc:
            return Response({"detail": exc.messages[0], "code": "sms_rate_limited"}, status=429)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        return Response({"detail": "Code envoyé par SMS."}, status=202)


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            user, created = verify_otp(request.data.get("phone", ""), request.data.get("code", ""))
        except (OtpError, DjangoValidationError) as exc:
            message = exc.messages[0] if isinstance(exc, DjangoValidationError) else str(exc)
            return Response({"detail": message}, status=400)
        return Response({"token": issue_token(user, request), "created": created, "user": UserSerializer(user).data})


class ProLoginView(APIView):
    """Comptes professionnels, étape 1 : email + mot de passe → code SMS."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "pro_login"

    def post(self, request):
        try:
            challenge, phone = services.pro_login(request.data.get("email", ""), request.data.get("password", ""))
        except LoginError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"challenge": challenge, "phone": phone, "detail": "Code envoyé par SMS."})


class ProVerifyView(APIView):
    """Comptes professionnels, étape 2 : code SMS → jeton de session."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "pro_login"

    def post(self, request):
        try:
            user = services.pro_verify(request.data.get("challenge", ""), request.data.get("code", ""))
        except LoginError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"token": issue_token(user, request), "user": UserSerializer(user).data})


class PasswordForgotView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password"

    def post(self, request):
        services.forgot_password(request.data.get("email", ""))
        return Response(
            {"detail": "Si un compte correspond à cet email, un lien vient de lui être envoyé."}, status=202
        )


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password"

    def post(self, request):
        try:
            services.reset_password(
                request.data.get("uid", ""), request.data.get("token", ""), request.data.get("password", "")
            )
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        return Response({"detail": "Mot de passe enregistré. Vous pouvez vous connecter."})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = services.update_profile(request.user, serializer.validated_data)
        return Response(UserSerializer(user).data)


class IdentityCheckView(CustomerOnly, APIView):
    """Vérification de l'identité numérique (eID Houwiyeti) auprès de l'ANRPTS, particuliers uniquement.

    POST : vérifie le NNI du profil. Réponse « outcome » : verified, no_eid ou not_verified (message
    neutre : rien n'indique au client pourquoi). ANRPTS injoignable : 503, code « unavailable ».
    """

    throttle_scope = "identity"  # interrogations limitées par compte (évite de tester des NNI en série)

    # Ce que voit l'app : le désaccord de téléphone n'est jamais révélé tel quel.
    PUBLIC_OUTCOMES = {
        IdentityCheck.Outcome.VALID: "verified",
        IdentityCheck.Outcome.NO_EID: "no_eid",
        IdentityCheck.Outcome.PHONE_MISMATCH: "not_verified",
    }

    def post(self, request):
        try:
            outcome = services.verify_identity(request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0], "code": exc.error_list[0].code or "invalid"}, status=400)
        if outcome == IdentityCheck.Outcome.UNAVAILABLE:
            return Response({"detail": "Service indisponible, réessayez dans quelques minutes.",
                             "code": "unavailable"}, status=503)
        return Response({"outcome": self.PUBLIC_OUTCOMES[outcome], "user": UserSerializer(request.user).data})


class LogoutView(APIView):
    """Déconnexion : le jeton de cet appareil est supprimé côté serveur (il ne vaut plus rien, même copié)."""

    def post(self, request):
        if request.auth is not None:
            request.auth.delete()
        return Response(status=204)


class LogoutOthersView(APIView):
    """« Déconnecter mes autres appareils » : toutes les connexions du compte sauf celle-ci."""

    def post(self, request):
        closed = revoke_others(request.user, keep=request.auth)
        record("user.logout_others", request.user, actor=request.user, closed=closed)
        return Response({"closed": closed})
