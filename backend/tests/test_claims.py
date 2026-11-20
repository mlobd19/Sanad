"""Sinistres : déclaration par le client, traitement par l'assureur (portail) ou l'équipe Sanad."""
import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.policies.models import Claim, ClaimPhoto, Policy

from .conftest import buy, simulate_callback


def jpeg(name="degats.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), "gray").save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def active_policy(client, insurer="mar", plate="1234AB00"):
    policy, pay = buy(client, plate=plate, insurer=insurer)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    p = Policy.objects.get(pk=policy["id"])
    if p.status == Policy.Status.PAID:  # MAR valide à la main : on simule la validation de l'assureur
        from apps.policies import services
        services.validate_policy(p, User.objects.get(phone="+22220000002"), "MAR-1")
    return Policy.objects.get(pk=policy["id"])


def declare(client, policy, photos=(), **overrides):
    data = {"kind": "accident", "occurred_on": str(timezone.localdate()), "place": "Carrefour Madrid, Nouakchott",
            "description": "Choc arrière à l'arrêt au feu.", "third_party_plate": " 9876 ab 00 ", "injuries": "false",
            **overrides}
    data = {k: v for k, v in data.items() if v is not None}
    if photos:
        data["photos"] = list(photos)
    return client.post(f"/api/policies/{policy.pk}/claims", data, format="multipart")


@pytest.fixture
def mar_agent(demo):
    client = APIClient()
    client.force_authenticate(User.objects.get(phone="+22220000002"))  # agent MAR
    return client


@pytest.fixture
def nasr_agent(demo):
    client = APIClient()
    client.force_authenticate(User.objects.get(phone="+22220000001"))  # agent NASR
    return client


def test_customer_declares_claim_with_photos(customer_client, outbox, settings, django_capture_on_commit_callbacks):
    policy = active_policy(customer_client)
    with django_capture_on_commit_callbacks(execute=True):
        resp = declare(customer_client, policy, photos=[jpeg(), jpeg("constat.jpg")])
    assert resp.status_code == 201, resp.data
    assert resp.data["number"].startswith(f"SIN-{timezone.localdate():%Y}-")
    assert resp.data["status"] == "submitted" and resp.data["photos"] == 2
    assert resp.data["third_party_plate"] == "9876 AB 00" and resp.data["injuries"] is False

    claim = Claim.objects.get()
    assert claim.declared_by.phone == "+22236000001"
    for photo in claim.photos.all():
        assert (settings.PRIVATE_MEDIA_ROOT / photo.file.name).is_file()  # stockage privé
        with pytest.raises(ValueError):
            photo.file.url
    assert not any(settings.MEDIA_ROOT.glob("claims/**/*"))
    assert AuditEvent.objects.filter(action="claim.declared").exists()
    message = outbox[-1]
    assert message["to"] == "+22236000001" and claim.number in message["body"] and "MAR" in message["body"]

    listed = customer_client.get(f"/api/policies/{policy.pk}/claims").data
    assert [c["number"] for c in listed] == [claim.number]


def test_claim_without_photo_is_accepted(customer_client):
    policy = active_policy(customer_client)
    assert declare(customer_client, policy, kind="theft").status_code == 201


@pytest.mark.parametrize("overrides, code", [
    ({"kind": "meteorite"}, "invalid_kind"),
    ({"occurred_on": "hier"}, "invalid_date"),
    ({"occurred_on": None}, "invalid_date"),
    ({"place": "  "}, "missing_fields"),
    ({"description": ""}, "missing_fields"),
    ({"description": "x" * 2001}, "too_long"),
])
def test_invalid_declarations(customer_client, overrides, code):
    policy = active_policy(customer_client)
    resp = declare(customer_client, policy, **overrides)
    assert resp.status_code == 400 and resp.data["code"] == code
    assert not Claim.objects.exists()


def test_date_must_be_covered_and_not_in_future(customer_client):
    policy = active_policy(customer_client)
    tomorrow = timezone.localdate() + timedelta(days=1)
    assert declare(customer_client, policy, occurred_on=str(tomorrow)).data["code"] == "future_date"
    before = policy.starts_on - timedelta(days=1)
    assert declare(customer_client, policy, occurred_on=str(before)).data["code"] == "outside_cover"


def test_photo_checks(customer_client):
    policy = active_policy(customer_client)
    assert declare(customer_client, policy, photos=[jpeg() for _ in range(7)]).data["code"] == "too_many_photos"
    fake = SimpleUploadedFile("x.jpg", b"<svg onload=alert(1)>", content_type="image/jpeg")
    assert declare(customer_client, policy, photos=[jpeg(), fake]).data["code"] == "invalid_type"
    assert not Claim.objects.exists() and not ClaimPhoto.objects.exists()  # rien n'est gardé à moitié


def test_only_active_or_expired_contracts(customer_client):
    policy, _ = buy(customer_client, plate="2222AB00")  # brouillon, jamais payé
    resp = declare(customer_client, Policy.objects.get(pk=policy["id"]))
    assert resp.status_code == 400 and resp.data["code"] == "policy_inactive"


def test_expired_contract_still_accepts_claim_within_cover(customer_client):
    policy = active_policy(customer_client)
    Policy.objects.filter(pk=policy.pk).update(status=Policy.Status.EXPIRED)
    assert declare(customer_client, policy).status_code == 201


def test_customer_cannot_declare_on_someone_elses_contract(customer_client, demo):
    policy = active_policy(customer_client)
    other = APIClient()
    from .conftest import login
    login(other, "+22236000099")
    assert declare(other, policy).status_code == 404
    assert other.get(f"/api/policies/{policy.pk}/claims").status_code == 404


def test_insurer_takes_then_closes_claim(customer_client, mar_agent, outbox, django_capture_on_commit_callbacks):
    policy = active_policy(customer_client)
    claim_id = declare(customer_client, policy, photos=[jpeg()]).data["id"]

    new = mar_agent.get("/api/insurer/claims?status=submitted").data
    assert [c["id"] for c in new] == [claim_id]
    row = new[0]
    assert row["customer"] == {"full_name": "Sidi Mohamed", "phone": "+22236000001"}
    assert row["policy"]["plate"] == "1234AB00" and len(row["photo_ids"]) == 1

    with django_capture_on_commit_callbacks(execute=True):
        taken = mar_agent.post(f"/api/insurer/claims/{claim_id}/take")
    assert taken.status_code == 200 and taken.data["status"] == "in_review"
    assert taken.data["handled_by"] == User.objects.get(phone="+22220000002").full_name
    assert "pris en charge" in outbox[-1]["body"]
    assert mar_agent.post(f"/api/insurer/claims/{claim_id}/take").status_code == 400  # déjà pris en charge

    assert mar_agent.post(f"/api/insurer/claims/{claim_id}/close", {"note": "  "}, format="json").status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        closed = mar_agent.post(f"/api/insurer/claims/{claim_id}/close",
                                {"note": "Expertise faite, indemnisation de 85 000 MRU."}, format="json")
    assert closed.status_code == 200 and closed.data["status"] == "closed"
    assert "85 000 MRU" in outbox[-1]["body"]

    seen = customer_client.get(f"/api/policies/{policy.pk}/claims").data[0]
    assert seen["status"] == "closed" and seen["closing_note"] == "Expertise faite, indemnisation de 85 000 MRU."
    assert {"claim.taken", "claim.closed"} <= set(AuditEvent.objects.values_list("action", flat=True))


def test_insurer_sees_and_opens_only_its_own_claims(customer_client, mar_agent, nasr_agent):
    policy = active_policy(customer_client)
    claim = declare(customer_client, policy, photos=[jpeg()]).data
    photo_id = Claim.objects.get().photos.get().pk

    assert nasr_agent.get("/api/insurer/claims").data == []
    assert nasr_agent.post(f"/api/insurer/claims/{claim['id']}/take").status_code == 404
    assert nasr_agent.get(f"/api/insurer/claims/{claim['id']}/photos/{photo_id}").status_code == 404

    resp = mar_agent.get(f"/api/insurer/claims/{claim['id']}/photos/{photo_id}")
    assert resp.status_code == 200 and resp["Content-Type"] == "image/jpeg"
    assert AuditEvent.objects.filter(action="claim.photo_viewed").count() == 1


def test_customers_cannot_use_insurer_endpoints(customer_client):
    assert customer_client.get("/api/insurer/claims").status_code == 403


def test_unknown_status_or_action(mar_agent):
    assert mar_agent.get("/api/insurer/claims?status=nimporte").status_code == 400
    assert mar_agent.post("/api/insurer/claims/1/delete").status_code == 404


def test_staff_handles_claim_in_backoffice(customer_client, outbox, django_capture_on_commit_callbacks):
    policy = active_policy(customer_client)
    declare(customer_client, policy, photos=[jpeg()])
    claim = Claim.objects.get()
    staff = User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                     is_staff=True, is_superuser=True)
    admin = Client()
    admin.force_login(staff)

    page = admin.get(f"/admin/policies/claim/{claim.pk}/change/")
    photo_url = f"/admin/policies/claim/photo/{claim.photos.get().pk}/"
    assert page.status_code == 200 and photo_url.encode() in page.content
    assert admin.get(photo_url).status_code == 200
    assert Client().get(photo_url).status_code == 302  # non connecté

    admin.post("/admin/policies/claim/", {"action": "take", "_selected_action": [claim.pk]})
    claim.refresh_from_db()
    assert claim.status == Claim.Status.IN_REVIEW and claim.handled_by == staff

    with django_capture_on_commit_callbacks(execute=True):
        admin.post("/admin/policies/claim/", {"action": "close", "_selected_action": [claim.pk], "sn_confirm": "1",
                                              "reason": "Dossier transmis et réglé par l'assureur."})
    claim.refresh_from_db()
    assert claim.status == Claim.Status.CLOSED and claim.closing_note.startswith("Dossier transmis")
    assert "Dossier transmis" in outbox[-1]["body"]
