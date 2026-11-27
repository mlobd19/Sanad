"""Assurance voyage « Monde entier » : catalogue, tarif, voyage, voyageurs, chevauchement, paiement,
attestations par voyageur, entreprise, sinistres. Une règle par test."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import IdentityCheck, User
from apps.attestations.models import Attestation
from apps.attestations.services import attestation_pdf, check
from apps.catalog.models import Product
from apps.notifications.backends import MemoryBackend
from apps.payments.models import Refund
from apps.policies import services
from apps.policies.models import Claim, InsuredAsset, Policy, Traveler

from .conftest import buy, login, simulate_callback
from .test_company import company_client

pytestmark = pytest.mark.django_db

ADULT, CHILD_NO_EID, UNKNOWN, DOWN = "2345678901", "0001234567", "1112223334", "9991112223"


def day(n: int) -> str:
    return (timezone.localdate() + timedelta(days=n)).isoformat()


def years_ago(n: int, extra_days: int = 0) -> str:
    today = timezone.localdate()
    return date(today.year - n, today.month, min(today.day, 28)).isoformat() if not extra_days else \
        (date(today.year - n, today.month, min(today.day, 28)) + timedelta(days=extra_days)).isoformat()


def new_trip(client, destinations=("ES",), start=7, end=20, base="/api"):
    resp = client.post(f"{base}/trips", {"destinations": list(destinations), "departure_on": day(start),
                                         "return_on": day(end)}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def add(client, trip, nni=ADULT, passport="B1234567", birth=None, name="", base="/api"):
    return client.post(f"{base}/trips/{trip['id']}/travelers", {
        "nni": nni, "passport_number": passport, "birth_date": birth or years_ago(30), "full_name": name,
    }, format="json")


def quotes(client, trip, base="/api"):
    resp = client.post(f"{base}/trips/{trip['id']}/quotes")
    assert resp.status_code == 201, resp.data
    return resp.data


def buy_trip(client, trip, insurer="nasr"):
    """Devis → contrat → paiement initié. Renvoie (police, paiement)."""
    quote = next(q for q in quotes(client, trip) if q["insurer_slug"] == insurer)
    policy = client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert policy.status_code == 201, policy.data
    pay = client.post(f"/api/policies/{policy.data['id']}/pay", {"provider": "simulated"}, format="json")
    assert pay.status_code == 201, pay.data
    return policy.data, pay.data


def active_trip_policy(client, auto_insurer, travelers=((ADULT, ""),)):
    trip = new_trip(client)
    for i, (nni, name) in enumerate(travelers):
        assert add(client, trip, nni=nni, passport=f"P{i}123456", name=name).status_code == 201
    policy, pay = buy_trip(client, trip, insurer="iman")
    assert simulate_callback(APIClient(), pay["reference"], pay["amount"]).data["outcome"] == "succeeded"
    return Policy.objects.get(pk=policy["id"])


# --- Catalogue et tarif ---------------------------------------------------------------------------------


def test_seed_offers_travel_at_nasr_mar_iman_only(demo):
    offers = Product.objects.filter(branch="travel", is_active=True)
    assert sorted(p.insurer.slug for p in offers) == ["iman", "mar", "nasr"]
    assert {p.name for p in offers} == {"Monde entier"} and all(p.is_indicative for p in offers)
    assert all(demo[slug].assistance_phone for slug in ("nasr", "mar", "iman"))


def test_every_travel_offer_covers_at_least_30000_eur_of_medical_costs(demo):
    assert all(p.limits["medical"] is None or p.limits["medical"] >= 30000
               for p in Product.objects.filter(branch="travel"))
    low = Product(insurer=demo["nasr"], branch="travel", code="low", name="Low", base_premium=1000,
                  limits={"medical": 20000})
    with pytest.raises(ValidationError):
        low.full_clean()
    # Une offre sous le plafond, même active en base, n'est jamais proposée.
    low.save()
    client = APIClient()
    login(client, "+22236000009")
    trip = new_trip(client)
    add(client, trip)
    assert "low" not in {q["product_code"] for q in quotes(client, trip)}


def test_travel_premium_by_duration_and_age_bands(demo):
    nasr = Product.objects.get(insurer=demo["nasr"], branch="travel")  # 2 600 MRU, 1-8 jours, 16-65 ans
    assert nasr.travel_premiums(8, [30]) == [2600]
    assert nasr.travel_premiums(9, [30]) == [4160]  # × 1,6
    assert nasr.travel_premiums(92, [30]) == [13520]  # × 5,2
    assert nasr.travel_premiums(8, [15, 16, 65, 66]) == [1300, 2600, 2600, 5200]  # enfant ½, plus de 65 ans × 2
    with pytest.raises(ValidationError):
        nasr.travel_premiums(93, [30])


def test_quote_total_is_the_sum_of_travelers(customer_client):
    trip = new_trip(customer_client, start=1, end=8)  # 8 jours
    add(customer_client, trip, birth=years_ago(30))
    add(customer_client, trip, nni="2345678902", passport="C7654321", birth=years_ago(10))
    offer = next(q for q in quotes(customer_client, trip) if q["insurer_slug"] == "nasr")
    assert offer["premium"] == 2600 + 1300 and offer["travelers"] == 2 and offer["days"] == 8
    assert offer["limits"]["medical"] == 50000 and offer["branch"] == "travel"


# --- Voyage : destinations et dates -------------------------------------------------------------------------


@pytest.mark.parametrize("start,end,code", [
    (-1, 5, "departure_past"),
    (5, 4, "return_before_departure"),
    (0, 92, "too_long"),  # 93 jours, départ et retour compris
])
def test_trip_dates_rules(customer_client, start, end, code):
    resp = customer_client.post("/api/trips", {"destinations": ["FR"], "departure_on": day(start),
                                               "return_on": day(end)}, format="json")
    assert resp.status_code == 400 and resp.data["code"] == code


def test_trip_of_one_day_and_of_92_days_are_accepted(customer_client):
    assert new_trip(customer_client, start=0, end=0)["days"] == 1
    assert new_trip(customer_client, start=0, end=91)["days"] == 92


@pytest.mark.parametrize("destinations,code", [([], "missing_destination"), (["XX"], "invalid_destination"),
                                               (["MR"], "invalid_destination")])
def test_destinations_are_iso_countries_abroad(customer_client, destinations, code):
    resp = customer_client.post("/api/trips", {"destinations": destinations, "departure_on": day(3),
                                               "return_on": day(9)}, format="json")
    assert resp.status_code == 400 and resp.data["code"] == code


def test_country_list_is_the_same_for_backend_and_app():
    root = Path(__file__).resolve().parents[2]
    backend = json.loads((root / "backend/apps/policies/countries.json").read_text(encoding="utf-8"))
    assert backend == json.loads((root / "frontend/lib/countries.json").read_text(encoding="utf-8"))
    assert len(backend) == 248 and all(c["fr"] and c["ar"] and c["en"] for c in backend)
    assert "MR" not in {c["code"] for c in backend}


# --- Voyageurs ---------------------------------------------------------------------------------------------------


def test_verified_traveler_takes_the_official_name(customer_client):
    trip = new_trip(customer_client)
    resp = add(customer_client, trip, nni="1234567890", name="Nom inventé")
    assert resp.status_code == 201
    traveler = resp.data["travelers"][0]
    assert traveler["full_name"] == "Sidi Mohamed" and traveler["full_name_ar"] == "سيدي محمد"
    assert traveler["verification"] == "verified"
    assert IdentityCheck.objects.filter(purpose="traveler", nni="1234567890", outcome="valid").exists()


def test_traveler_without_eid_is_declared_with_passport_name(customer_client):
    trip = new_trip(customer_client)
    assert add(customer_client, trip, nni=CHILD_NO_EID).data["code"] == "name_required"
    resp = add(customer_client, trip, nni=CHILD_NO_EID, name="Mariem  mint Sidi", birth=years_ago(6))
    assert resp.status_code == 201
    traveler = resp.data["travelers"][0]
    assert traveler["verification"] == "declared" and traveler["full_name"] == "MARIEM MINT SIDI"


@pytest.mark.parametrize("nni,code,message", [
    (UNKNOWN, "not_found", "Ce NNI est introuvable. Vérifiez les chiffres saisis et réessayez."),
    (DOWN, "unavailable", "Service indisponible, réessayez dans quelques minutes."),
])
def test_unknown_or_unreachable_nni_refuses_the_traveler(customer_client, nni, code, message):
    trip = new_trip(customer_client)
    resp = add(customer_client, trip, nni=nni)
    assert resp.status_code == 400 and resp.data["code"] == code and resp.data["detail"] == message
    assert not Traveler.objects.exists()


def test_traveler_check_endpoint_returns_the_name_before_adding(customer_client):
    resp = customer_client.post("/api/travelers/check", {"nni": "1234567890"}, format="json")
    assert resp.data == {"status": "verified", "full_name": "Sidi Mohamed", "full_name_ar": "سيدي محمد"}
    assert customer_client.post("/api/travelers/check", {"nni": CHILD_NO_EID}, format="json").data["status"] == "declared"
    # Gardé 30 min : l'ajout qui suit n'interroge pas l'ANRPTS une seconde fois.
    add(customer_client, new_trip(customer_client), nni="1234567890")
    assert IdentityCheck.objects.filter(purpose="traveler", nni="1234567890").count() == 1


def test_traveler_fields_are_checked(customer_client):
    trip = new_trip(customer_client)
    assert add(customer_client, trip, passport="12").data["code"] == "invalid_passport"
    assert add(customer_client, trip, birth=day(1)).data["code"] == "invalid_birth_date"
    assert add(customer_client, trip).status_code == 201
    assert add(customer_client, trip).data["code"] == "already_added"


def test_at_most_9_travelers_for_a_customer(customer_client):
    trip = new_trip(customer_client)
    for i in range(9):
        assert add(customer_client, trip, nni=f"23456789{i:02d}", passport=f"P{i}000000").status_code == 201
    assert add(customer_client, trip, nni="2345678999", passport="P9000000").data["code"] == "too_many_travelers"


# --- Chevauchement : un voyageur, un seul contrat voyage à la fois -------------------------------------------------


def test_overlap_by_nni_is_refused_at_quote(customer_client, auto_insurer):
    active_trip_policy(customer_client, auto_insurer)  # voyage J+7 → J+20
    other = new_trip(customer_client, destinations=("FR",), start=15, end=30)
    resp = add(customer_client, other)
    assert resp.status_code == 400 and resp.data["code"] == "traveler_overlap"
    later = new_trip(customer_client, destinations=("FR",), start=21, end=30)  # après le retour : possible
    assert add(customer_client, later).status_code == 201
    assert quotes(customer_client, later)


def test_overlap_is_checked_again_when_payment_is_confirmed(customer_client, outbox,
                                                            django_capture_on_commit_callbacks):
    first, second = new_trip(customer_client), new_trip(customer_client, destinations=("IT",), start=10, end=12)
    add(customer_client, first)
    add(customer_client, second)
    _, pay1 = buy_trip(customer_client, first)
    p2, pay2 = buy_trip(customer_client, second)  # aucun contrat payé encore : devis possible
    simulate_callback(APIClient(), pay1["reference"], pay1["amount"])
    with django_capture_on_commit_callbacks(execute=True):
        simulate_callback(APIClient(), pay2["reference"], pay2["amount"])
    policy = Policy.objects.get(pk=p2["id"])
    assert policy.status == Policy.Status.REFUSED
    assert Refund.objects.filter(payment__policy=policy).exists()
    assert "déjà assuré sur ces dates" in outbox[-1]["body"]


def test_travelers_are_locked_once_the_trip_is_paid(customer_client):
    trip = new_trip(customer_client)
    add(customer_client, trip)
    _, pay = buy_trip(customer_client, trip)
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    resp = add(customer_client, trip, nni="2345678902", passport="C7654321")
    assert resp.status_code == 400 and resp.data["code"] == "locked"


def test_quote_must_match_the_current_travelers(customer_client):
    trip = new_trip(customer_client)
    add(customer_client, trip)
    quote = quotes(customer_client, trip)[0]
    add(customer_client, trip, nni="2345678902", passport="C7654321")
    resp = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json")
    assert resp.status_code == 400 and resp.data["code"] == "quote_outdated"


# --- Paiement et cycle de vie ------------------------------------------------------------------------------------


def test_customer_identity_is_verified_before_paying_a_trip(customer_client):
    User.objects.filter(phone="+22236000001").update(kyc_status=User.KycStatus.NONE)
    trip = new_trip(customer_client)
    add(customer_client, trip)
    quote = quotes(customer_client, trip)[0]
    policy = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json").data  # brouillon possible
    resp = customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 400 and resp.data["code"] == "kyc_required"


def test_trip_policy_covers_departure_to_return(customer_client):
    trip = new_trip(customer_client, start=3, end=17)
    add(customer_client, trip)
    policy, _ = buy_trip(customer_client, trip)
    assert (policy["starts_on"], policy["ends_on"]) == (day(3), day(17))
    assert policy["branch"] == "travel" and policy["trip"]["destinations"] == ["ES"]


def test_one_attestation_per_traveler_and_travel_sms(customer_client, auto_insurer, outbox,
                                                     django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        policy = active_trip_policy(customer_client, auto_insurer,
                                    travelers=((ADULT, ""), (CHILD_NO_EID, "Mariem Mint Sidi")))
    assert policy.status == Policy.Status.ACTIVE
    atts = list(policy.attestations.order_by("pk"))
    assert len(atts) == 2 and {a.traveler.nni for a in atts} == {ADULT, CHILD_NO_EID}
    assert all(a.number.startswith(f"SN-{timezone.localdate().year}-") for a in atts)
    assert "Espagne" in outbox[-1]["body"] and "voyage" in outbox[-1]["body"]
    data = customer_client.get(f"/api/policies/{policy.pk}").data
    assert all(t["attestation"]["number"] for t in data["trip"]["travelers"])


def test_public_verification_masks_traveler_data(customer_client, auto_insurer):
    policy = active_trip_policy(customer_client, auto_insurer)
    att = policy.attestations.get()
    result = check(att.token)
    assert result["status"] == "not_yet_valid" and result["product"] == "travel"
    assert result["holder"] != att.traveler.full_name and "***" in result["holder"]
    assert result["passport"].endswith("456") and "P0123" not in result["passport"]
    assert result["destinations"] == "Espagne" and "birth" not in json.dumps(result)
    page = APIClient().get(f"/v/{att.token}").content.decode()
    assert "Passport" in page and att.traveler.passport_number not in page


def test_travel_pdf_is_trilingual_specimen_without_premium(customer_client, auto_insurer, settings):
    settings.ATTESTATION_SPECIMEN = True
    policy = active_trip_policy(customer_client, auto_insurer)
    att = policy.attestations.get()
    pdf = attestation_pdf(att)
    assert pdf.startswith(b"%PDF")
    from pypdf import PdfReader
    import io
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for expected in ("TRAVEL INSURANCE CERTIFICATE", "SPÉCIMEN", "Schengen", "30 000 €", att.traveler.passport_number,
                     policy.product.insurer.assistance_phone):
        assert expected in text, expected
    assert str(policy.premium) not in text.replace(" ", "")


def test_cancelling_a_trip_revokes_every_attestation(customer_client, auto_insurer, demo):
    policy = active_trip_policy(customer_client, auto_insurer, travelers=((ADULT, ""), ("2345678902", "")))
    staff = User.objects.create_user("+22230000077", role=User.Role.STAFF)
    services.cancel_policy(policy, staff, "Voyage annulé")
    assert set(policy.attestations.values_list("status", flat=True)) == {Attestation.Status.REVOKED}


def test_no_renewal_reminder_for_a_trip(customer_client, auto_insurer):
    policy = active_trip_policy(customer_client, auto_insurer)
    days = (policy.ends_on - timezone.localdate()).days
    assert policy not in services.policies_due_for_reminder(days)


def test_trips_never_show_in_the_vehicle_list(customer_client):
    add(customer_client, new_trip(customer_client))
    assert all(a["kind"] == "vehicle" for a in customer_client.get("/api/assets").data)
    trip_asset = InsuredAsset.objects.get(kind="trip")
    assert customer_client.post(f"/api/assets/{trip_asset.pk}/quotes").status_code == 404


def test_auto_rules_unchanged_by_trips(customer_client):
    """Un voyage vers « ES » ne bloque pas un véhicule, et inversement (règles séparées)."""
    add(customer_client, new_trip(customer_client))
    policy, pay = buy(customer_client, plate="1234ES00")
    assert simulate_callback(APIClient(), pay["reference"], pay["amount"]).data["outcome"] == "succeeded"


# --- Entreprise : missions des salariés ---------------------------------------------------------------------------


def test_company_mission_for_employees_without_accounts(demo):
    client = company_client()
    trip = new_trip(client, base="/api/company")
    assert add(client, trip, base="/api/company").status_code == 201
    assert add(client, trip, nni=CHILD_NO_EID, passport="D1112223", name="Salarié Sans Eid",
               base="/api/company").status_code == 201
    assert not User.objects.filter(nni=ADULT).exists()  # pas de compte Sanad pour les salariés
    quote = next(q for q in quotes(client, trip, base="/api/company") if q["insurer_slug"] == "mar")
    order = client.post("/api/company/orders", {"quote_ids": [quote["id"]]}, format="json")
    assert order.status_code == 201, order.data
    pay = client.post(f"/api/company/orders/{order.data['id']}/pay", {"provider": "simulated"}, format="json")
    assert pay.status_code == 201
    assert simulate_callback(APIClient(), pay.data["reference"], pay.data["amount"]).data["outcome"] == "succeeded"
    assert client.get("/api/company/trips").data[0]["locked"] is True


def test_company_mission_payment_needs_verification_and_ceiling(demo, settings):
    unverified = company_client(nif="00777777", email="a@nv.test", phone="+22246000077", verified=False)
    trip = new_trip(unverified, base="/api/company")
    add(unverified, trip, base="/api/company")
    quote = quotes(unverified, trip, base="/api/company")[0]
    order = unverified.post("/api/company/orders", {"quote_ids": [quote["id"]]}, format="json").data
    resp = unverified.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 400 and "vérifiée" in resp.data["detail"]

    client = company_client()
    trip = new_trip(client, base="/api/company")
    add(client, trip, base="/api/company")
    quote = quotes(client, trip, base="/api/company")[0]
    order = client.post("/api/company/orders", {"quote_ids": [quote["id"]]}, format="json").data
    settings.PAYMENT_MAX_AMOUNT = order["total"] - 1
    resp = client.post(f"/api/company/orders/{order['id']}/pay", {"provider": "simulated"}, format="json")
    assert resp.status_code == 400 and "plafond" in resp.data["detail"]


def test_companies_and_customers_never_see_each_other_trips(demo, customer_client):
    a = company_client()
    b = company_client(nif="00999999", email="admin@sahel.test", phone="+22246000050", legal_name="Sahel Logistique")
    trip = new_trip(a, base="/api/company")
    assert b.get(f"/api/company/trips/{trip['id']}").status_code == 404
    assert add(b, trip, base="/api/company").status_code == 404
    assert b.get("/api/company/trips").data == []
    assert customer_client.get(f"/api/trips/{trip['id']}").status_code == 404
    mine = new_trip(customer_client)
    assert a.get(f"/api/company/trips/{mine['id']}").status_code == 404


def test_company_mission_allows_up_to_50_travelers(demo):
    from apps.policies.travel import MAX_TRAVELERS

    assert MAX_TRAVELERS == {"customer": 9, "company": 50}


# --- Sinistres ---------------------------------------------------------------------------------------------------------


def test_travel_claim_kinds_and_traveler(customer_client, auto_insurer):
    policy = active_trip_policy(customer_client, auto_insurer)
    Policy.objects.filter(pk=policy.pk).update(starts_on=timezone.localdate() - timedelta(days=2))
    traveler = policy.asset.trip.travelers.get()
    base = {"occurred_on": day(-1), "place": "Madrid", "description": "Consultation aux urgences"}
    resp = customer_client.post(f"/api/policies/{policy.pk}/claims", {**base, "kind": "accident"}, format="multipart")
    assert resp.status_code == 400 and resp.data["code"] == "invalid_kind"
    resp = customer_client.post(f"/api/policies/{policy.pk}/claims",
                                {**base, "kind": "medical", "traveler": traveler.pk}, format="multipart")
    assert resp.status_code == 201 and resp.data["traveler"] == traveler.full_name
    assert Claim.objects.get().traveler == traveler


def test_auto_claim_refuses_travel_kinds(customer_client, auto_insurer):
    policy, pay = buy(customer_client, insurer="iman")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    Policy.objects.filter(pk=policy["id"]).update(starts_on=timezone.localdate() - timedelta(days=2))
    resp = customer_client.post(f"/api/policies/{policy['id']}/claims", {
        "kind": "medical", "occurred_on": day(-1), "place": "Nouakchott", "description": "x"}, format="multipart")
    assert resp.data["code"] == "invalid_kind"


# --- Portail assureur ---------------------------------------------------------------------------------------------------


def test_insurer_filters_policies_and_commissions_by_product(customer_client, auto_insurer):
    active_trip_policy(customer_client, auto_insurer)
    _, pay = buy(customer_client, insurer="iman", plate="5555AB00")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    agent = APIClient()
    agent.force_authenticate(User.objects.get(phone="+22220000004", role=User.Role.INSURER_AGENT))
    travel = agent.get("/api/insurer/policies?branch=travel").data
    assert [p["branch"] for p in travel] == ["travel"]
    assert travel[0]["trip"]["travelers"][0]["verification"] == "verified"
    assert {p["branch"] for p in agent.get("/api/insurer/policies").data} == {"auto", "travel"}
    assert [c["branch"] for c in agent.get("/api/insurer/commissions?branch=travel").data["items"]] == ["travel"]
    assert agent.get("/api/insurer/policies?branch=boat").status_code == 400


def test_declared_name_is_visible_to_the_insurer(customer_client, auto_insurer):
    active_trip_policy(customer_client, auto_insurer, travelers=((CHILD_NO_EID, "Enfant Sans Eid"),))
    agent = APIClient()
    agent.force_authenticate(User.objects.get(phone="+22220000004", role=User.Role.INSURER_AGENT))
    traveler = agent.get("/api/insurer/policies?branch=travel").data[0]["trip"]["travelers"][0]
    assert traveler["verification"] == "declared" and traveler["full_name"] == "ENFANT SANS EID"


def test_traveler_checks_have_their_own_rate(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["traveler_check"] == "30/hour"
    from apps.policies.api import TravelerCheckView, TravelerListView

    assert TravelerCheckView.throttle_scope == TravelerListView.throttle_scope == "traveler_check"
    assert MemoryBackend  # (journal des SMS : utilisé par les autres tests)


# --- Back-office ----------------------------------------------------------------------------------------------------


def test_backoffice_filters_by_product_and_shows_travelers(customer_client, auto_insurer, settings):
    from django.test import Client

    settings.DEBUG, settings.BACKOFFICE_2FA = True, "off"
    policy = active_trip_policy(customer_client, auto_insurer, travelers=((CHILD_NO_EID, "Enfant Sans Eid"),))
    _, pay = buy(customer_client, insurer="iman", plate="7777AB00")
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    staff = User.objects.create_user("+22230000088", password="Equipe-Sanad-2026", role=User.Role.STAFF,
                                     is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(staff)
    page = client.get("/admin/policies/policy/?produit=travel").content.decode()
    # Liste filtrée sur le voyage : le contrat voyage (codes des pays) sans le contrat auto.
    assert ">ES<" in page.replace(" ", "") or "ES</span>" in page
    assert "7777AB00" not in page and "Voyage" in page
    detail = client.get(f"/admin/policies/policy/{policy.pk}/change/").content.decode()
    assert "ENFANT SANS EID" in detail and "Déclaré (sans eID)" in detail and "Espagne" in detail
