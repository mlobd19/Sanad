"""Informations publiques sur l'instance, lues par l'app au démarrage (bandeau « Démonstration »)."""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class MetaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"demo_mode": bool(settings.DEMO_MODE)})
