"""Durées de couverture proposées : 3, 6 ou 12 mois."""
from datetime import date, timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import SHORT_TERM_RATES
from apps.policies.models import Policy, add_months

from .conftest import simulate_callback
from .test_company import add_vehicles, company_client


def add_asset(client, plate="2468AB00"):
    return client.post(
        "/api/assets", {"reference": plate, "attributes": {"fiscal_power": 8, "usage": "personal"}}, format="json"
    ).data


def quotes_for(client, asset_id, months=None):
    body = {} if months is None else {"months": months}
    return client.post(f"/api/assets/{asset_id}/quotes", body, format="json")


def by_offer(quotes):
    return {(q["insurer_slug"], q["product_code"]): q for q in quotes}


def test_quotes_default_to_twelve_months(customer_client):
    asset = add_asset(customer_client)
    quotes = quotes_for(customer_client, asset["id"]).data
    assert quotes and {q["duration_months"] for q in quotes} == {12}


def test_short_durations_apply_short_term_rate(customer_client):
    asset = add_asset(customer_client)
    annual = by_offer(quotes_for(customer_client, asset["id"], 12).data)
    for months in (3, 6):
        resp = quotes_for(customer_client, asset["id"], months)
        assert resp.status_code == 201, resp.data
        short = by_offer(resp.data)
        assert short.keys() == annual.keys()
        for key, quote in short.items():
            assert quote["duration_months"] == months
            assert quote["premium"] < annual[key]["premium"]
            expected = annual[key]["premium"] * SHORT_TERM_RATES[months]
            assert abs(quote["premium"] - expected) <= 1  # arrondi au MRU


def test_rc_stays_identical_across_insurers_for_each_duration(customer_client):
    asset = add_asset(customer_client)
    for months in (3, 6, 12):
        quotes = quotes_for(customer_client, asset["id"], months).data
        assert len({q["premium"] for q in quotes if q["product_code"] == "rc"}) == 1


def test_unsupported_duration_is_rejected(customer_client):
    asset = add_asset(customer_client)
    for months in (1, 24, "abc"):
        resp = quotes_for(customer_client, asset["id"], months)
        assert resp.status_code == 400 and "3, 6 ou 12 mois" in resp.data["detail"]


def test_add_months_handles_month_ends():
    assert add_months(date(2026, 12, 15), 3) == date(2027, 3, 15)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert Policy.compute_end(date(2026, 12, 15), 3) == date(2027, 3, 14)


def test_policy_period_follows_quote_duration(customer_client):
    asset = add_asset(customer_client)
    start = timezone.localdate() + timedelta(days=10)
    quote = next(q for q in quotes_for(customer_client, asset["id"], 3).data if q["product_code"] == "tiers-etendu")
    resp = customer_client.post("/api/policies", {"quote_id": quote["id"], "starts_on": str(start)}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["duration_months"] == 3
    assert resp.data["premium"] == quote["premium"]
    assert resp.data["ends_on"] == str(Policy.compute_end(start, 3))


def test_short_cover_blocks_overlapping_cover(customer_client):
    """Une couverture de 6 mois bloque toute autre couverture du véhicule jusqu'à son dernier jour."""
    asset = add_asset(customer_client)
    quote = next(q for q in quotes_for(customer_client, asset["id"], 6).data if q["product_code"] == "rc")
    policy = customer_client.post("/api/policies", {"quote_id": quote["id"]}, format="json").data
    pay = customer_client.post(f"/api/policies/{policy['id']}/pay", {"provider": "simulated"}, format="json").data
    simulate_callback(APIClient(), pay["reference"], pay["amount"])
    ends_on = Policy.objects.get(pk=policy["id"]).ends_on
    assert ends_on == Policy.compute_end(timezone.localdate(), 6)

    nxt = next(q for q in quotes_for(customer_client, asset["id"], 6).data if q["product_code"] == "rc")
    resp = customer_client.post("/api/policies", {"quote_id": nxt["id"]}, format="json")
    assert resp.status_code == 400 and "déjà couvert" in resp.data["detail"]


def test_fleet_offers_and_order_use_chosen_duration(db, demo):
    client = company_client()
    ids = add_vehicles(client, "1001AB00", "1002AB00")
    annual = client.post("/api/company/quotes", {"asset_ids": ids}, format="json").data
    offers = client.post("/api/company/quotes", {"asset_ids": ids, "months": 6}, format="json").data
    assert {o["duration_months"] for o in offers} == {6}
    totals = {(o["insurer"], o["product_code"]): o["total"] for o in annual}
    offer = next(o for o in offers if o["product_code"] == "tiers-etendu")
    assert offer["total"] < totals[(offer["insurer"], "tiers-etendu")]

    start = timezone.localdate() + timedelta(days=5)
    resp = client.post("/api/company/orders", {"quote_ids": [line["quote_id"] for line in offer["lines"]],
                                               "starts_on": str(start)}, format="json")
    assert resp.status_code == 201, resp.data
    assert {(p["duration_months"], p["ends_on"]) for p in resp.data["policies"]} == {
        (6, str(Policy.compute_end(start, 6)))}


def test_fleet_order_cannot_mix_durations(db, demo):
    client = company_client()
    first, second = add_vehicles(client, "2001AB00", "2002AB00")
    q3 = client.post("/api/company/quotes", {"asset_ids": [first], "months": 3}, format="json").data[0]
    q12 = next(o for o in client.post("/api/company/quotes", {"asset_ids": [second]}, format="json").data
               if o["insurer"] == q3["insurer"] and o["product_code"] == q3["product_code"])
    resp = client.post("/api/company/orders", {"quote_ids": [q3["lines"][0]["quote_id"], q12["lines"][0]["quote_id"]]},
                       format="json")
    assert resp.status_code == 400 and "une seule durée" in resp.data["detail"]
