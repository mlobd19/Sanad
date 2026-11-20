from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import record

from .models import KycDocument, User
from . import identity, services
from .services import LoginError, OtpError, request_otp, verify_otp

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "phone", "email", "full_name", "nni", "language", "kyc_status", "role"]
        read_only_fields = ["id", "phone", "email", "kyc_status", "role"]


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            request_otp(request.data.get("phone", ""))
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
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "created": created, "user": UserSerializer(user).data})


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
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


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


class IdentityCheckView(APIView):
    """Vérification d'identité auprès du registre national (ANRPTS), particuliers uniquement.

    GET : la vérification automatique est-elle disponible ? POST : lance la vérification
    avec le NNI et le nom du profil. Erreurs avec un « code » que l'app traduit.
    """

    throttle_scope = "identity"

    def get_throttles(self):
        # Seule l'interrogation du registre est limitée (évite de tester des NNI en série).
        return super().get_throttles() if self.request.method == "POST" else []

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.user.is_pro:
            self.permission_denied(request, message="Réservé aux comptes particuliers.")

    def get(self, request):
        return Response({"available": services.identity_check_available()})

    def post(self, request):
        try:
            check = services.verify_identity(request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0], "code": exc.error_list[0].code or "invalid"}, status=400)
        except identity.IdentityUnavailable:
            return Response({"detail": "Le registre national ne répond pas. Réessayez plus tard.",
                             "code": "unavailable"}, status=503)
        return Response({"outcome": check.outcome, "user": UserSerializer(request.user).data})


class KycDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KycDocument
        fields = ["id", "kind", "file", "status", "uploaded_at"]
        read_only_fields = ["id", "status", "uploaded_at"]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_file(self, f):
        if f.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("Fichier trop lourd (8 Mo maximum).")
        if getattr(f, "content_type", None) not in ALLOWED_TYPES:
            raise serializers.ValidationError("Formats acceptés : JPEG, PNG, PDF.")
        return f


class KycDocumentView(APIView):
    def get(self, request):
        return Response(KycDocumentSerializer(request.user.documents.all(), many=True).data)

    def post(self, request):
        serializer = KycDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(user=request.user)
        if request.user.kyc_status == User.KycStatus.NONE:
            request.user.kyc_status = User.KycStatus.PENDING
            request.user.save(update_fields=["kyc_status"])
        record("kyc.document_uploaded", doc, actor=request.user, kind=doc.kind)
        return Response(KycDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)
