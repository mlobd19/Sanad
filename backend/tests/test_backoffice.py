"""Back-office : connexion par code SMS, accueil « À traiter », décisions avec motif, lecture seule, langues."""
import re

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import translation
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.notifications.backends import MemoryBackend
from apps.backoffice.management.commands.compile_translations import source_messages
from apps.companies import services as company_services
from apps.companies.models import Company, CompanyDocument, Membership
from apps.payments.models import Payment, Refund
from apps.policies.models import Policy

from .conftest import buy, simulate_callback

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(db):
    return User.objects.create_user("+22230000000", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                    is_staff=True, is_superuser=True, full_name="Équipe Sanad")


@pytest.fixture
def admin_client(staff):
    client = Client()
    client.force_login(staff)
    return client


def make_company(nif="00123456", docs=("nif", "rc")) -> Company:
    company = Company.objects.create(legal_name="TransMaur SARL", nif=nif, rc_number="NKC-2019-B-1234")
    admin_user = User.objects.create_user(f"+2224600{nif[-4:]}", role=User.Role.COMPANY_MEMBER,
                                          email=f"admin{nif}@transmaur.test", full_name="Fatimetou")
    Membership.objects.create(company=company, user=admin_user, role=Membership.Role.ADMIN)
    for kind in docs:
        CompanyDocument.objects.create(company=company, kind=kind,
                                       file=SimpleUploadedFile(f"{kind}.pdf", b"%PDF", content_type="application/pdf"))
    return company


def paid_policy(customer_client, plate="1234AB00") -> Policy:
    policy, pay = buy(customer_client, plate=plate)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    return Policy.objects.get(pk=policy["id"])


# --- Accès ---------------------------------------------------------------------------------


def test_backoffice_is_served_to_staff_only(admin_client, customer_client, demo):
    assert admin_client.get("/admin/").status_code == 200
    agent = Client()
    agent.force_login(User.objects.get(email="agent@mar.test"))
    assert agent.get("/admin/").status_code == 302  # renvoyé vers la connexion
    login = Client().post("/admin/login/", {"username": "+22220000002", "password": "x"})
    assert login.status_code == 200 and b"errornote" in login.content


@pytest.fixture
def sms_mode(settings):
    """Code SMS au lieu de l'application d'authentification : permis en DEBUG seulement."""
    settings.DEBUG, settings.BACKOFFICE_2FA = True, "sms"


def last_sms_code(phone="+22230000000") -> str:
    sms = [m for m in MemoryBackend.outbox if m["channel"] == "sms" and m["to"] == phone][-1]
    return re.search(r"\b(\d{6})\b", sms["body"]).group(1)


def test_staff_logs_in_with_password_then_sms_code(staff, sms_mode):
    client = Client()
    resp = client.post("/admin/login/?next=/admin/policies/policy/",
                       {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    assert resp.status_code == 302 and resp.url == "/admin/login/code/"
    assert client.get("/admin/").status_code == 302  # pas encore connecté : le mot de passe ne suffit pas
    page = client.get("/admin/login/code/")
    assert page.status_code == 200 and "+222 •• •• •• 00" in page.content.decode()

    resp = client.post("/admin/login/code/", {"code": "000000" if last_sms_code() != "000000" else "111111"})
    assert resp.status_code == 200 and b"errornote" in resp.content
    resp = client.post("/admin/login/code/", {"code": last_sms_code()})
    assert resp.status_code == 302 and resp.url == "/admin/policies/policy/"
    assert client.get("/admin/").status_code == 200
    assert AuditEvent.objects.filter(action="user.login", data__method="password+sms").exists()
    assert client.get("/admin/login/code/").status_code == 302  # étape terminée : plus de code en attente


def test_sms_code_cannot_be_reused_or_brute_forced(staff, settings, sms_mode):
    client = Client()
    client.post("/admin/login/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    good = last_sms_code()
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        client.post("/admin/login/code/", {"code": wrong})
    client.post("/admin/login/code/", {"code": good})  # trop tard : le code est épuisé
    assert client.get("/admin/").status_code == 302


def test_code_resend_waits_a_minute(staff, monkeypatch, sms_mode):
    from apps.backoffice import site

    client = Client()
    client.post("/admin/login/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    first = last_sms_code()
    resp = client.post("/admin/login/code/", {"resend": "1"})
    assert b"errornote" in resp.content and last_sms_code() == first  # trop tôt
    now = site.time.time()
    monkeypatch.setattr(site.time, "time", lambda: now + site.RESEND_DELAY + 1)
    resp = client.post("/admin/login/code/", {"resend": "1"})
    assert b"sn-notice" in resp.content
    assert client.post("/admin/login/code/", {"code": last_sms_code()}).status_code == 302


def test_staff_account_locks_after_repeated_bad_passwords(staff, settings):
    client = Client()
    for _ in range(settings.PRO_LOGIN_MAX_FAILURES):
        client.post("/admin/login/", {"username": "+22230000000", "password": "mauvais"})
    resp = client.post("/admin/login/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    assert resp.status_code == 200 and b"errornote" in resp.content  # verrouillé, même avec le bon mot de passe
    assert not [m for m in MemoryBackend.outbox if m["to"] == "+22230000000"]


def test_logout_returns_to_sanad_home(admin_client):
    resp = admin_client.post("/admin/logout/")
    assert resp.status_code == 302 and resp.url == "/"
    assert admin_client.get("/admin/").status_code == 302  # session bien fermée


def test_login_pages_link_back_to_sanad(staff):
    client = Client()
    assert b'href="/">' in client.get("/admin/login/").content
    client.post("/admin/login/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    assert b'href="/">' in client.get("/admin/login/totp/").content


def test_second_factor_can_be_disabled_in_development_only(staff, settings):
    settings.DEBUG, settings.BACKOFFICE_2FA = True, "off"
    resp = Client().post("/admin/login/?next=/admin/", {"username": "+22230000000", "password": "Equipe-Sanad-2026"})
    assert resp.status_code == 302 and resp.url == "/admin/"


# --- Accueil « À traiter » ---------------------------------------------------------------------


def test_home_counts_what_needs_attention(admin_client, customer_client, demo):
    make_company("00111111")                 # pièces complètes : à vérifier
    make_company("00222222", docs=("nif",))  # en attente de pièces
    paid_policy(customer_client)
    payment = Payment.objects.get(status=Payment.Status.SUCCEEDED)
    Refund.objects.create(payment=payment, amount=1000, status=Refund.Status.FAILED)

    todo = {item["label"]: item for item in admin_client.get("/admin/").context["todo"]}

    assert todo["Entreprises à vérifier"]["count"] == 1
    assert "1 en attente de pièces" in todo["Entreprises à vérifier"]["extra"]
    assert todo["Polices payées, en attente de l'assureur"]["count"] == 1
    assert todo["Remboursements en échec"]["count"] == 1
    assert todo["Entreprises à vérifier"]["url"] == "/admin/companies/company/?status__exact=pending"


def test_menu_is_grouped_by_trade(admin_client):
    sections = [str(s["name"]) for s in admin_client.get("/admin/").context["app_list"]]
    assert sections[:5] == ["Clients", "Entreprises", "Contrats", "Paiements", "Catalogue"]
    assert sections[-1] == "Technique"


# --- Décisions ----------------------------------------------------------------------------------


def test_company_decision_panel_verify_and_reject(admin_client, django_capture_on_commit_callbacks):
    company = make_company()
    page = admin_client.get(f"/admin/companies/company/{company.pk}/change/")
    assert b"sn-decision" in page.content and b"verifier/" in page.content

    resp = admin_client.post(f"/admin/companies/company/{company.pk}/refuser/", {"sn_confirm": "1", "reason": ""})
    assert resp.status_code == 200 and "Le motif est obligatoire." in resp.content.decode()
    company.refresh_from_db()
    assert company.status == Company.Status.PENDING

    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(f"/admin/companies/company/{company.pk}/refuser/",
                          {"sn_confirm": "1", "reason": "RC illisible"})
    company.refresh_from_db()
    assert company.status == Company.Status.REJECTED and company.rejection_reason == "RC illisible"
    assert "RC illisible" in mail.outbox[-1].body

    admin_client.post(f"/admin/companies/company/{company.pk}/verifier/")
    company.refresh_from_db()
    assert company.status == Company.Status.VERIFIED


def test_verify_refused_while_documents_missing(admin_client):
    company = make_company(docs=("nif",))
    admin_client.post(f"/admin/companies/company/{company.pk}/verifier/")
    company.refresh_from_db()
    assert company.status == Company.Status.PENDING


def test_refuse_policies_action_requires_reason(admin_client, customer_client, demo):
    policy = paid_policy(customer_client)
    url = "/admin/policies/policy/"
    form = admin_client.post(url, {"action": "refuse_selected", "_selected_action": [policy.pk]})
    assert form.status_code == 200 and b"id_reason" in form.content

    admin_client.post(url, {"action": "refuse_selected", "_selected_action": [policy.pk], "sn_confirm": "1",
                            "reason": "Véhicule hors catégorie"})
    policy.refresh_from_db()
    assert policy.status == Policy.Status.REFUSED and policy.refusal_reason == "Véhicule hors catégorie"
    assert Payment.objects.get(policy=policy).status == Payment.Status.REFUNDED


def test_failed_refund_marked_done_by_hand(admin_client, customer_client, demo):
    paid_policy(customer_client)
    refund = Refund.objects.create(payment=Payment.objects.get(), amount=500, status=Refund.Status.FAILED)
    admin_client.post("/admin/payments/refund/", {"action": "mark_done_manually", "_selected_action": [refund.pk],
                                                  "sn_confirm": "1", "reason": "BKL-778899"})
    refund.refresh_from_db()
    assert refund.status == Refund.Status.DONE and refund.external_ref == "BKL-778899"


# --- Lecture seule --------------------------------------------------------------------------------


@pytest.mark.parametrize("path", [
    "/admin/payments/payment/add/", "/admin/policies/policy/add/", "/admin/attestations/attestation/add/",
    "/admin/policies/quote/add/", "/admin/companies/company/add/",
])
def test_money_and_contracts_cannot_be_created_by_hand(admin_client, path):
    assert admin_client.get(path).status_code == 403


# --- Langues ----------------------------------------------------------------------------------------


def test_backoffice_switches_to_arabic(admin_client):
    resp = admin_client.post("/admin/i18n/setlang/", {"language": "ar", "next": "/admin/"})
    assert resp.status_code == 302
    page = admin_client.get("/admin/").content.decode()
    assert 'dir="rtl"' in page
    assert "للمعالجة" in page and "الشركات" in page  # « À traiter », « Entreprises »
    admin_client.post("/admin/i18n/setlang/", {"language": "fr", "next": "/admin/"})
    assert "À traiter" in admin_client.get("/admin/").content.decode()


def test_every_backoffice_text_has_an_arabic_translation():
    """Tout texte marqué à traduire dans le code doit exister en arabe (catalogue compilé à jour)."""
    with translation.override("ar"):
        missing = [m for m in source_messages() if translation.gettext(m) == m]
    assert missing == [], f"Sans traduction arabe ({len(missing)}) : {missing[:10]}"
