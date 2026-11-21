"""PDF de l'attestation : contenu, mention spécimen, droits d'accès, révocation."""
import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attestations.models import Attestation
from apps.audit.models import AuditEvent
from apps.policies import services as policy_services
from apps.policies.models import Policy

from .conftest import buy, login, simulate_callback

pytestmark = pytest.mark.django_db


def agent(phone: str) -> APIClient:
    client = APIClient()
    client.force_authenticate(User.objects.get(phone=phone))
    return client


@pytest.fixture
def attestation(customer_client, demo) -> Attestation:
    """Police MAR payée puis validée par l'agent MAR."""
    policy, pay = buy(customer_client, plate="4321AB01", insurer="mar")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent("+22220000002").post(f"/api/insurer/policies/{policy['id']}/validate")
    return Attestation.objects.get(policy_id=policy["id"])


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) == 1
    return reader.pages[0].extract_text()


def pdf_fonts(content: bytes) -> set[str]:
    page = PdfReader(io.BytesIO(content)).pages[0]
    return {str(font["/BaseFont"]) for font in page["/Resources"]["/Font"].values()}


def test_customer_downloads_bilingual_pdf(customer_client, attestation):
    resp = customer_client.get(f"/api/attestations/{attestation.id}/pdf")

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert f'filename="attestation-{attestation.number}.pdf"' in resp["Content-Disposition"]
    assert resp.content.startswith(b"%PDF")
    text = pdf_text(resp.content)
    for expected in (attestation.number, "43 21 AB 01", "Sidi Mohamed", "1234567890", "MAR",
                     "Mauritanienne d'Assurance et de Réassurance", "ATTESTATION D'ASSURANCE AUTOMOBILE"):
        assert expected in text, expected
    policy = attestation.policy
    assert f"du {policy.starts_on:%d/%m/%Y} au {policy.ends_on:%d/%m/%Y}" in text
    # Texte arabe mis en forme avec sa propre police, en plus de la police latine.
    assert any("NotoKufiArabic" in f for f in pdf_fonts(resp.content))
    assert any("NotoSans" in f for f in pdf_fonts(resp.content))
    assert AuditEvent.objects.filter(action="attestation.pdf_downloaded").exists()


def test_pdf_carries_specimen_mention_by_default(customer_client, attestation, settings):
    assert "SPÉCIMEN" in pdf_text(customer_client.get(f"/api/attestations/{attestation.id}/pdf").content)

    settings.ATTESTATION_SPECIMEN = False
    assert "SPÉCIMEN" not in pdf_text(customer_client.get(f"/api/attestations/{attestation.id}/pdf").content)


def test_pdf_shows_premium_nowhere(customer_client, attestation):
    text = pdf_text(customer_client.get(f"/api/attestations/{attestation.id}/pdf").content)
    assert "MRU" not in text and str(attestation.policy.premium) not in text.replace(" ", "")


def test_pdf_with_official_logo(customer_client, attestation):
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), "white").save(buffer, format="PNG")
    insurer = attestation.policy.product.insurer
    insurer.logo.save("mar.png", ContentFile(buffer.getvalue()), save=True)

    resp = customer_client.get(f"/api/attestations/{attestation.id}/pdf")

    assert resp.status_code == 200
    assert len(PdfReader(io.BytesIO(resp.content)).pages[0].images) == 2  # logo + QR code


def test_pdf_access_rules(attestation):
    url = f"/api/attestations/{attestation.id}/pdf"
    assert agent("+22220000002").get(url).status_code == 200  # agent de la compagnie (MAR)
    assert agent("+22220000001").get(url).status_code == 404  # agent d'une autre compagnie (NASR)
    other = APIClient()
    login(other, "+22236000077")
    assert other.get(url).status_code == 404  # autre client
    assert APIClient().get(url).status_code in (401, 403)  # anonyme


def test_revoked_attestation_cannot_be_downloaded(customer_client, attestation):
    policy = Policy.objects.get(pk=attestation.policy_id)
    policy_services.cancel_policy(policy, User.objects.get(phone="+22220000002"), reason="Vente du véhicule")

    resp = customer_client.get(f"/api/attestations/{attestation.id}/pdf")

    assert resp.status_code == 410
    assert "révoquée" in resp.data["detail"]
