import base64
from datetime import date

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import signing
from .models import Attestation
from .services import AttestationRevoked, attestation_for, attestation_pdf, check, qr_png


class VerifyView(APIView):
    """Vérification publique : ce que voit l'agent de contrôle. Données personnelles masquées."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "verify"

    def get(self, request, token):
        return Response(check(token))


class PublicKeyView(APIView):
    """Clé publique pour la vérification hors ligne dans l'app de contrôle."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        vk = signing.public_key()
        return Response({"algorithm": "Ed25519", "key_id": signing.key_id(vk),
                         "public_key": base64.b64encode(bytes(vk)).decode()})


class QrCodeView(APIView):
    def get(self, request, attestation_id):
        att = get_object_or_404(Attestation, pk=attestation_id, policy__customer=request.user)
        return HttpResponse(qr_png(att), content_type="image/png")


class AttestationPdfView(APIView):
    """PDF de l'attestation, pour le client propriétaire ou un agent de la compagnie."""

    def get(self, request, attestation_id):
        try:
            att = attestation_for(request.user, attestation_id)
            pdf = attestation_pdf(att, actor=request.user)
        except Attestation.DoesNotExist:
            return Response({"detail": "Attestation introuvable."}, status=404)
        except AttestationRevoked as exc:
            return Response({"detail": exc.messages[0]}, status=410)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="attestation-{att.number}.pdf"'
        return response


def _day(iso: str) -> str:
    """« 2026-11-21 » → « 21/11/2026 » pour l'agent de contrôle (l'API garde le format ISO)."""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def verify_page(request, token):
    """Page web ouverte en scannant le QR avec n'importe quel téléphone."""
    result = check(token)
    if result.get("valid_from"):
        result = {**result, "valid_from": _day(result["valid_from"]), "valid_to": _day(result["valid_to"])}
    return render(request, "attestations/verify.html", {"result": result})
