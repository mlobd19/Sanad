"""Lecture de la carte grise : pré-remplissage du formulaire véhicule, photo jamais conservée."""
import base64
import io
import json
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.policies import registration_scan

from .test_company import company_client

CARD = {"is_registration_card": True, "plate": " 1234  ab 00 ", "make": "Toyota", "model": "Hilux", "fiscal_power": 9}


def photo(fmt="JPEG", size=(2400, 1600)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format=fmt)
    return SimpleUploadedFile(f"carte.{fmt.lower()}", buf.getvalue(), content_type=f"image/{fmt.lower()}")


def scan(client, upload):
    return client.post("/api/assets/scan", {"image": upload}, format="multipart")


class FakeAnthropic:
    """Remplace anthropic.Anthropic : garde la requête, renvoie une réponse préparée."""

    calls: list = []
    response = None

    def __init__(self, **kwargs):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        FakeAnthropic.calls.append(kwargs)
        return FakeAnthropic.response


@pytest.fixture
def claude(settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "test-key"
    FakeAnthropic.calls = []
    FakeAnthropic.response = SimpleNamespace(
        stop_reason="end_turn", _request_id="req_test",
        content=[SimpleNamespace(type="text", text=json.dumps(CARD))],
    )
    monkeypatch.setattr(registration_scan.anthropic, "Anthropic", FakeAnthropic)
    return FakeAnthropic


def test_scan_prefills_vehicle_fields(customer_client, claude, settings):
    resp = scan(customer_client, photo())
    assert resp.status_code == 200, resp.data
    assert resp.data == {"reference": "1234AB00", "make": "Toyota Hilux", "fiscal_power": 9}

    request = claude.calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"]["format"]["schema"] == registration_scan.SCHEMA
    assert request["fallbacks"] == "default"
    image = request["messages"][0]["content"][0]
    assert image["source"]["media_type"] == "image/jpeg"
    # La photo est réduite avant l'envoi.
    sent = Image.open(io.BytesIO(base64.b64decode(image["source"]["data"])))
    assert max(sent.size) <= registration_scan.MAX_SIDE

    # Rien n'est conservé : aucun fichier écrit, l'audit ne garde que les champs trouvés.
    assert not any(settings.MEDIA_ROOT.rglob("*.*"))
    event = AuditEvent.objects.get(action="vehicle.registration_scanned")
    assert event.data == {"found": ["fiscal_power", "make", "reference"]}


def test_unreadable_fields_come_back_empty(customer_client, claude):
    claude.response.content[0].text = json.dumps(
        {"is_registration_card": True, "plate": "", "make": "", "model": "", "fiscal_power": 400})
    resp = scan(customer_client, photo())
    assert resp.status_code == 200
    assert resp.data == {"reference": "", "make": "", "fiscal_power": None}


def test_other_document_is_rejected(customer_client, claude):
    claude.response.content[0].text = json.dumps({**CARD, "is_registration_card": False})
    resp = scan(customer_client, photo())
    assert resp.status_code == 400 and resp.data["code"] == "not_card"


def test_file_that_is_not_an_image_is_rejected(customer_client, claude):
    bogus = SimpleUploadedFile("carte.jpg", b"pas une image", content_type="image/jpeg")
    resp = scan(customer_client, bogus)
    assert resp.status_code == 400 and resp.data["code"] == "unreadable"
    assert claude.calls == []


def test_missing_photo(customer_client, claude):
    resp = customer_client.post("/api/assets/scan", {}, format="multipart")
    assert resp.status_code == 400 and resp.data["code"] == "missing"


def test_without_api_key_scan_is_unavailable(customer_client):
    resp = scan(customer_client, photo())
    assert resp.status_code == 503 and resp.data["code"] == "unavailable"


def test_refusal_or_truncated_answer_is_a_failed_read(customer_client, claude):
    for stop in ("refusal", "max_tokens"):
        claude.response.stop_reason = stop
        resp = scan(customer_client, photo())
        assert resp.status_code == 502 and resp.data["code"] == "failed"


def test_api_error_is_a_failed_read(customer_client, claude, monkeypatch):
    def boom(self, **kwargs):
        raise registration_scan.anthropic.APIConnectionError(request=None)
    monkeypatch.setattr(FakeAnthropic, "create", boom)
    resp = scan(customer_client, photo())
    assert resp.status_code == 502 and resp.data["code"] == "failed"


def test_company_member_can_scan_but_not_insurer_agent(db, demo, agent_client, claude):
    assert scan(company_client(), photo()).status_code == 200
    assert scan(agent_client, photo()).status_code == 403


def test_scan_requires_login(db, claude):
    assert scan(APIClient(), photo()).status_code == 401


def test_app_is_told_whether_scan_is_available(customer_client, settings):
    assert customer_client.get("/api/assets/scan").data == {"available": False}
    settings.ANTHROPIC_API_KEY = "test-key"
    assert customer_client.get("/api/assets/scan").data == {"available": True}


def test_availability_check_does_not_use_scan_quota():
    from rest_framework.test import APIRequestFactory
    from rest_framework.throttling import ScopedRateThrottle

    from apps.policies.api import RegistrationScanView

    factory = APIRequestFactory()
    for method, throttled in (("get", False), ("post", True)):
        view = RegistrationScanView()
        view.throttle_classes = [ScopedRateThrottle]  # les tests désactivent les limites par défaut
        view.request = getattr(factory, method)("/api/assets/scan")
        throttles = view.get_throttles()
        assert any(isinstance(t, ScopedRateThrottle) for t in throttles) is throttled
