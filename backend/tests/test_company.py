"""Espace entreprise : inscription, vérification, flotte, devis groupés, commande, isolation."""
import io
import re
import zipfile

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies import services as company_services
from apps.companies.models import Company
from apps.notifications.backends import MemoryBackend
from apps.payments.models import Payment, Refund
from apps.policies.models import Policy

from .conftest import login, simulate_callback

pytestmark = pytest.mark.django_db

PASSWORD = "Flotte-Nouakchott-2026"


def sms_code(phone: str) -> str:
    sms = [m for m in MemoryBackend.outbox if m["channel"] == "sms" and m["to"] == phone][-1]
    return re.search(r"\b(\d{6})\b", sms["body"]).group(1)


def signup(client, *, nif="00123456", email="admin@transmaur.test", phone="+22246000001", legal_name="TransMaur SARL"):
    return client.post("/api/company/signup", {
        "legal_name": legal_name, "nif": nif, "rc_number": "NKC-2019-B-1234", "address": "Tevragh Zeina, Nouakchott",
        "full_name": "Fatimetou Mint Sidi", "email": email, "phone": phone, "password": PASSWORD,
    }, format="json")


def company_client(nif="00123456", email="admin@transmaur.test", phone="+22246000001", verified=True,
                   legal_name="TransMaur SARL") -> APIClient:
    """Inscription complète (SMS compris), pièces déposées, entreprise vérifiée si demandé."""
    client = APIClient()
    resp = signup(client, nif=nif, email=email, phone=phone, legal_name=legal_name)
    assert resp.status_code == 201, resp.data
    resp = client.post("/api/company/signup/verify", {"challenge": resp.data["challenge"], "code": sms_code(phone)},
                       format="json")
    assert resp.status_code == 200, resp.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
    for kind in ("nif", "rc"):
        upload = SimpleUploadedFile(f"{kind}.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        assert client.post("/api/company/documents", {"kind": kind, "file": upload}, format="multipart").status_code == 201
    if verified:
        company = Company.objects.get(nif=nif)
        company_services.verify_company(company, User.objects.get(email=email))
    return client


def add_vehicles(client, *plates):
    ids = []
    for plate in plates:
        resp = client.post("/api/company/fleet", {"reference": plate, "attributes": {"fiscal_power": 9, "usage": "commercial",
                                                                                    "make": "Toyota Hilux"}},
                           format="json")
        assert resp.status_code == 201, resp.data
        ids.append(resp.data["id"])
    return ids


def order_offer(client, asset_ids, insurer="MAR", product_code="tiers-etendu"):
    offers = client.post("/api/company/quotes", {"asset_ids": asset_ids}, format="json").data
    offer = next(o for o in offers if o["insurer"] == insurer and o["product_code"] == product_code)
    resp = client.post("/api/company/orders", {"quote_ids": [line["quote_id"] for line in offer["lines"]]}, format="json")
    assert resp.status_code == 201, resp.data
    return offer, resp.data


def agent(phone="+22220000002") -> APIClient:
    client = APIClient()
    client.force_authenticate(User.objects.get(phone=phone, role=User.Role.INSURER_AGENT))
    return client


# --- Inscription et vérification ----------------------------------------------------------


def test_signup_confirms_phone_by_sms_then_logs_in(demo):
    client = APIClient()
    resp = signup(client)
    assert resp.status_code == 201
    assert resp.data["phone"] == "+222 •• •• •• 01"
    admin = User.objects.get(email="admin@transmaur.test")
    assert not admin.is_active  # tant que le SMS n'est pas confirmé

    verified = client.post("/api/company/signup/verify",
                           {"challenge": resp.data["challenge"], "code": sms_code("+22246000001")}, format="json")
    assert verified.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Token {verified.data['token']}")
    me = client.get("/api/company/me").data
    assert me["company"]["status"] == "pending"
    assert me["company"]["nif"] == "00123456"
    assert me["company"]["rc_number"] == "NKC-2019-B-1234"  # mise en forme conservée
    assert me["company"]["missing_documents"] == ["nif", "rc"]
    assert me["member"]["role"] == "admin"

    # Ensuite : connexion normale des comptes pro (email + mot de passe + SMS).
    pro = APIClient().post("/api/auth/pro/login", {"email": "admin@transmaur.test", "password": PASSWORD}, format="json")
    assert pro.status_code == 200


def test_signup_rejects_duplicates_and_weak_password(demo):
    company_client(verified=False)
    assert signup(APIClient(), email="autre@transmaur.test").data["detail"] == \
        "Une entreprise est déjà inscrite avec ce NIF."
    assert signup(APIClient(), nif="99999999").data["detail"] == "Un compte existe déjà avec cet email."
    weak = APIClient().post("/api/company/signup", {
        "legal_name": "X", "nif": "77777777", "rc_number": "RC77777", "full_name": "Y",
        "email": "x@y.test", "phone": "+22246000009", "password": "court"}, format="json")
    assert weak.status_code == 400


def test_abandoned_signup_can_be_restarted(demo):
    signup(APIClient())  # jamais confirmé par SMS
    assert signup(APIClient()).status_code == 201
    assert Company.objects.filter(nif="00123456").count() == 1


def test_same_phone_for_personal_and_company_accounts(demo):
    personal = APIClient()
    login(personal, "+22246000001")
    client = company_client(phone="+22246000001")
    assert User.objects.filter(phone="+22246000001").count() == 2
    # Les deux espaces restent étanches.
    assert personal.get("/api/company/me").status_code == 403
    assert client.get("/api/policies").status_code == 403
    assert client.get("/api/assets").status_code == 403


def test_payment_blocked_until_company_is_verified(demo):
    client = company_client(verified=False)
    ids = add_vehicles(client, "1001AA00")
    _, order = order_offer(client, ids)  # devis et commande possibles
    resp = client.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 400
    assert "vérifiée" in resp.data["detail"]


def test_verification_requires_both_documents_and_notifies(demo):
    client = APIClient()
    resp = signup(client)
    client.post("/api/company/signup/verify", {"challenge": resp.data["challenge"], "code": sms_code("+22246000001")},
                format="json")
    company = Company.objects.get(nif="00123456")
    staff = User.objects.create_user("+22230000000", role=User.Role.STAFF)
    with pytest.raises(ValidationError, match="Pièces manquantes"):
        company_services.verify_company(company, staff)
    with pytest.raises(ValidationError, match="motif"):
        company_services.reject_company(company, staff, "")


def test_reject_then_new_document_restarts_review(demo, django_capture_on_commit_callbacks):
    client = company_client(verified=False)
    company = Company.objects.get(nif="00123456")
    staff = User.objects.create_user("+22230000000", role=User.Role.STAFF)
    with django_capture_on_commit_callbacks(execute=True):
        company_services.reject_company(company, staff, "RC illisible")
    assert "RC illisible" in mail.outbox[-1].body
    upload = SimpleUploadedFile("rc.pdf", b"%PDF-1.4 v2", content_type="application/pdf")
    client.post("/api/company/documents", {"kind": "rc", "file": upload}, format="multipart")
    assert client.get("/api/company/me").data["company"]["status"] == "pending"


# --- Membres ---------------------------------------------------------------------------------


def test_admin_invites_a_manager_who_cannot_invite(demo):
    admin = company_client()
    resp = admin.post("/api/company/members", {"full_name": "Moussa Ba", "email": "moussa@transmaur.test",
                                               "phone": "+22246000002", "role": "manager"}, format="json")
    assert resp.status_code == 201
    assert "TransMaur SARL" in mail.outbox[-1].body
    assert "/entreprise/mot-de-passe?uid=" in mail.outbox[-1].body

    manager = APIClient()
    manager.force_authenticate(User.objects.get(email="moussa@transmaur.test"))
    assert manager.post("/api/company/members", {"full_name": "Z", "email": "z@t.test", "phone": "+22246000003"},
                        format="json").status_code == 403
    upload = SimpleUploadedFile("nif.pdf", b"%PDF", content_type="application/pdf")
    assert manager.post("/api/company/documents", {"kind": "nif", "file": upload}, format="multipart").status_code == 403
    assert manager.get("/api/company/fleet").status_code == 200  # mais gère la flotte


# --- Flotte ----------------------------------------------------------------------------------


def test_fleet_csv_import_reports_bad_lines(demo):
    client = company_client()
    add_vehicles(client, "2002BB00")
    csv_content = (
        "immatriculation;marque;cv;usage\n"
        "3003CC00;Hyundai H1;8;commercial\n"
        "4004DD00;Toyota Corolla;6;personnel\n"
        "2002BB00;Doublon;9;commercial\n"
        "5005EE00;Sans CV;;taxi\n"
        "6006FF00;Usage inconnu;7;location\n"
    ).encode()
    upload = SimpleUploadedFile("flotte.csv", csv_content, content_type="text/csv")
    resp = client.post("/api/company/fleet/import", {"file": upload}, format="multipart")

    assert resp.status_code == 200
    assert resp.data["created"] == ["3003CC00", "4004DD00"]
    assert [e["line"] for e in resp.data["errors"]] == [4, 5, 6]
    assert "déjà dans la flotte" in resp.data["errors"][0]["message"]
    assert len(client.get("/api/company/fleet").data) == 3


# --- Devis groupés, commande, paiement ----------------------------------------------------------


def test_group_quote_order_single_payment_and_partial_refusal(demo, django_capture_on_commit_callbacks):
    client = company_client()
    ids = add_vehicles(client, "7007GG00", "8008HH00", "9009II00")
    offer, order = order_offer(client, ids)
    assert len(offer["lines"]) == 3 and offer["total"] == sum(line["premium"] for line in offer["lines"])
    assert order["total"] == offer["total"]
    assert {p["status"] for p in order["policies"]} == {"draft"}

    pay = client.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json")
    assert pay.status_code == 201
    assert pay.data["amount"] == offer["total"]  # un seul paiement pour toute la commande
    simulate_callback(APIClient(), pay.data["reference"], pay.data["amount"])
    assert set(Policy.objects.filter(order_id=order["id"]).values_list("status", flat=True)) == {"paid"}

    # L'agent MAR voit l'entreprise cliente, valide deux contrats et en refuse un.
    pending = agent().get("/api/insurer/policies?status=paid").data
    assert {p["company"]["legal_name"] for p in pending} == {"TransMaur SARL"}
    assert {p["payment_provider"] for p in pending} == {"simulated"}  # payé via la commande
    first, second, third = sorted(pending, key=lambda p: p["plate"])
    agent().post(f"/api/insurer/policies/{first['id']}/validate")
    agent().post(f"/api/insurer/policies/{second['id']}/validate")
    with django_capture_on_commit_callbacks(execute=True):
        agent().post(f"/api/insurer/policies/{third['id']}/refuse", {"reason": "Véhicule hors catégorie"}, format="json")

    payment = Payment.objects.get(order_id=order["id"], status=Payment.Status.SUCCEEDED)
    refund = Refund.objects.get(payment=payment)
    assert refund.amount == third["premium"] and refund.policy_id == third["id"]  # seule la ligne refusée
    statuses = {p["plate"]: p["status"] for p in client.get("/api/company/policies").data}
    assert statuses == {"7007GG00": "active", "8008HH00": "active", "9009II00": "refused"}
    fleet = {v["reference"]: v["policy"] for v in client.get("/api/company/fleet").data}
    assert fleet["9009II00"] is None  # refusé : plus de contrat en cours
    assert fleet["7007GG00"]["status"] == "active"

    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/company/attestations.zip").content))
    assert sorted(n.split("-")[-1] for n in archive.namelist()) == ["7007GG00.pdf", "8008HH00.pdf"]


def test_order_above_payment_ceiling_is_refused(demo, settings):
    client = company_client()
    _, order = order_offer(client, add_vehicles(client, "1111JJ00", "2222JJ00"))
    settings.PAYMENT_MAX_AMOUNT = order["total"] - 1
    resp = client.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 400
    assert "plafond" in resp.data["detail"]


# --- Isolation entre entreprises -----------------------------------------------------------------


def test_companies_never_see_each_other(demo):
    a = company_client()
    b = company_client(nif="00999999", email="admin@sahel.test", phone="+22246000050", legal_name="Sahel Logistique")
    a_ids = add_vehicles(a, "3333KK00")
    _, a_order = order_offer(a, a_ids)

    assert b.get("/api/company/fleet").data == []
    assert b.get("/api/company/policies").data == []
    assert b.get(f"/api/company/orders/{a_order['id']}").status_code == 404
    assert b.post(f"/api/company/orders/{a_order['id']}/pay", {"provider": "simulated"}, format="json").status_code == 404
    assert b.post("/api/company/quotes", {"asset_ids": a_ids}, format="json").status_code == 400
    a_quote = a.post("/api/company/quotes", {"asset_ids": a_ids}, format="json").data[0]["lines"][0]["quote_id"]
    assert b.post("/api/company/orders", {"quote_ids": [a_quote]}, format="json").status_code == 400
    assert [m["email"] for m in b.get("/api/company/members").data] == ["admin@sahel.test"]
    policy = Policy.objects.get(order_id=a_order["id"])
    assert b.get(f"/api/attestations/{policy.pk}/pdf").status_code == 404


def test_customers_and_agents_cannot_use_company_api(customer_client):
    for path in ("/api/company/me", "/api/company/fleet", "/api/company/policies"):
        assert customer_client.get(path).status_code == 403
        assert agent().get(path).status_code == 403
