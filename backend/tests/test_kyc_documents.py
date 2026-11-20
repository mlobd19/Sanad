"""Pièce d'identité déposée dans l'app : secours du registre, fichier privé, consultation par l'équipe."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from apps.accounts.models import KycDocument, User
from apps.audit.models import AuditEvent


@pytest.fixture
def customer_client(customer_client):
    """Client démo dont l'identité n'est pas encore vérifiée."""
    User.objects.filter(phone="+22236000001", role=User.Role.CUSTOMER).update(kyc_status=User.KycStatus.NONE)
    return customer_client


def jpeg(name="cni.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (800, 500), "white").save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def pdf(name="passeport.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 piece", content_type="application/pdf")


def upload(client, file, kind="id_card"):
    return client.post("/api/me/documents", {"kind": kind, "file": file}, format="multipart")


def customer():
    return User.objects.get(phone="+22236000001", role=User.Role.CUSTOMER)


def test_upload_puts_account_in_review_and_keeps_file_private(customer_client, settings):
    resp = upload(customer_client, jpeg())
    assert resp.status_code == 201, resp.data
    assert set(resp.data) == {"id", "kind", "status", "uploaded_at"}  # jamais d'URL du fichier
    assert customer().kyc_status == User.KycStatus.PENDING

    doc = KycDocument.objects.get()
    assert doc.file.name.endswith(".jpg")
    stored = settings.PRIVATE_MEDIA_ROOT / doc.file.name
    assert stored.is_file()
    assert not any(settings.MEDIA_ROOT.glob("kyc/**/*"))  # rien dans le dossier public
    with pytest.raises(ValueError):
        doc.file.url
    assert AuditEvent.objects.filter(action="kyc.document_uploaded").exists()

    listed = customer_client.get("/api/me/documents").data
    assert [(d["kind"], d["status"]) for d in listed] == [("id_card", "pending")]


def test_pdf_passport_is_accepted(customer_client):
    assert upload(customer_client, pdf(), kind="passport").status_code == 201
    assert KycDocument.objects.get().file.name.endswith(".pdf")


@pytest.mark.parametrize("make_file, kind, code", [
    (lambda: SimpleUploadedFile("cni.jpg", b"<html>pas une image</html>", content_type="image/jpeg"), "id_card",
     "invalid_type"),
    (lambda: SimpleUploadedFile("cni.gif", b"GIF89a\x01\x00\x01\x00", content_type="image/gif"), "id_card",
     "invalid_type"),
    (jpeg, "vehicle_registration", "invalid_kind"),
    (jpeg, "", "invalid_kind"),
])
def test_rejected_uploads(customer_client, make_file, kind, code):
    resp = upload(customer_client, make_file(), kind=kind)
    assert resp.status_code == 400 and resp.data["code"] == code
    assert not KycDocument.objects.exists()
    assert customer().kyc_status == User.KycStatus.NONE


def test_file_too_large(customer_client, monkeypatch):
    from apps.accounts import services
    monkeypatch.setattr(services, "KYC_MAX_BYTES", 100)
    resp = upload(customer_client, jpeg())
    assert resp.status_code == 400 and resp.data["code"] == "too_large"


def test_missing_file(customer_client):
    resp = customer_client.post("/api/me/documents", {"kind": "id_card"}, format="multipart")
    assert resp.status_code == 400 and resp.data["code"] == "missing"


def test_pending_documents_are_capped(customer_client):
    for _ in range(3):
        assert upload(customer_client, jpeg()).status_code == 201
    resp = upload(customer_client, jpeg())
    assert resp.status_code == 400 and resp.data["code"] == "too_many"


@pytest.mark.parametrize("status, code", [("verified", "already_verified"), ("rejected", "rejected")])
def test_no_upload_once_decided(customer_client, status, code):
    User.objects.filter(phone="+22236000001").update(kyc_status=status)
    resp = upload(customer_client, jpeg())
    assert resp.status_code == 400 and resp.data["code"] == code


def test_pro_accounts_cannot_upload(agent_client):
    assert agent_client.get("/api/me/documents").status_code == 403
    assert upload(agent_client, jpeg()).status_code == 403


def test_pending_review_still_blocks_payment_until_staff_validates(customer_client):
    upload(customer_client, jpeg())
    asset = customer_client.post("/api/assets", {"reference": "5555AB00",
                                                 "attributes": {"fiscal_power": 8, "usage": "personal"}},
                                 format="json").data
    quote = customer_client.post(f"/api/assets/{asset['id']}/quotes").data[0]
    policy = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json").data
    pay = lambda: customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json")
    assert pay().data["code"] == "kyc_required"

    staff = User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                     is_staff=True, is_superuser=True)
    admin = Client()
    admin.force_login(staff)
    resp = admin.post("/admin/accounts/user/", {"action": "mark_kyc_verified", "_selected_action": [customer().pk]})
    assert resp.status_code == 302
    assert customer().kyc_status == User.KycStatus.VERIFIED
    assert KycDocument.objects.get().status == KycDocument.Status.ACCEPTED
    assert pay().status_code == 201


def test_staff_opens_document_and_access_is_logged(customer_client):
    upload(customer_client, jpeg())
    doc = KycDocument.objects.get()
    url = f"/admin/accounts/user/piece/{doc.pk}/"

    assert Client().get(url).status_code == 302  # non connecté : renvoyé vers la connexion

    staff = User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                     is_staff=True, is_superuser=True)
    admin = Client()
    admin.force_login(staff)
    resp = admin.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/jpeg" and "no-store" in resp["Cache-Control"]
    assert b"".join(resp.streaming_content).startswith(b"\xff\xd8")
    event = AuditEvent.objects.get(action="kyc.document_viewed")
    assert event.actor == staff and event.data == {"user_id": doc.user_id}

    page = admin.get(f"/admin/accounts/user/{doc.user_id}/change/")
    assert url.encode() in page.content  # le lien « Ouvrir » du back-office passe par cette vue


def test_staff_without_view_permission_cannot_open(customer_client):
    upload(customer_client, jpeg())
    doc = KycDocument.objects.get()
    limited = User.objects.create_user("+22230000001", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                       is_staff=True)
    client = Client()
    client.force_login(limited)
    assert client.get(f"/admin/accounts/user/piece/{doc.pk}/").status_code == 403
    assert not AuditEvent.objects.filter(action="kyc.document_viewed").exists()
