"""Deux usages seulement : personnel ou commercial (plus de « taxi »)."""
from datetime import timedelta
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.catalog.models import Product, TariffFactor
from apps.policies.models import InsuredAsset, Policy, Quote, VehicleUsage

from .conftest import buy
from .test_company import add_vehicles, company_client

pytestmark = pytest.mark.django_db


def new_asset(client, usage, plate="6602BA00", power=6):
    return client.post("/api/assets", {"reference": plate, "attributes": {"fiscal_power": power, "usage": usage}},
                       format="json")


# --- « taxi » refusé partout ---------------------------------------------------------------------

def test_only_two_usages():
    assert VehicleUsage.values == ["personal", "commercial"]


def test_api_refuses_taxi_for_customers(customer_client):
    resp = new_asset(customer_client, "taxi")
    assert resp.status_code == 400 and "personnel ou commercial" in str(resp.data)
    assert not InsuredAsset.objects.exists()


def test_api_refuses_taxi_for_company_fleets(demo):
    client = company_client()
    resp = client.post("/api/company/fleet", {"reference": "7007GG00",
                                              "attributes": {"fiscal_power": 9, "usage": "taxi"}}, format="json")
    assert resp.status_code == 400 and "personnel ou commercial" in resp.data["detail"]
    report = client.post("/api/company/fleet/import", {"file": _csv("8008HH00;Toyota;9;taxi\n")}, format="multipart")
    assert report.data["created"] == [] and "personnel ou commercial" in report.data["errors"][0]["message"]


def _csv(lines: str):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("flotte.csv", ("immatriculation;marque;cv;usage\n" + lines).encode(), content_type="text/csv")


def test_old_taxi_vehicle_cannot_be_quoted(customer_client):
    asset = InsuredAsset.objects.create(owner=_customer(), reference="9009II00",
                                        attributes={"fiscal_power": 6, "usage": "taxi"})  # créé avant la règle
    resp = customer_client.post(f"/api/assets/{asset.pk}/quotes")
    assert resp.status_code == 400


def _customer():
    from apps.accounts.models import User

    return User.objects.filter(role=User.Role.CUSTOMER).first()


def test_demo_catalogue_has_no_taxi_factor(demo):
    assert not TariffFactor.objects.filter(attribute="usage", equals="taxi").exists()
    assert TariffFactor.objects.filter(attribute="usage", equals="commercial").exists()


# --- Devis : coefficient de l'usage commercial ----------------------------------------------------

def test_commercial_quote_uses_the_commercial_coefficient(customer_client, demo):
    personal = new_asset(customer_client, "personal", plate="1010AA00").data
    commercial = new_asset(customer_client, "commercial", plate="2020AA00").data
    p_quotes = {q["product_code"] + q["insurer_slug"]: q["premium"]
                for q in customer_client.post(f"/api/assets/{personal['id']}/quotes").data}
    c_quotes = {q["product_code"] + q["insurer_slug"]: q["premium"]
                for q in customer_client.post(f"/api/assets/{commercial['id']}/quotes").data}
    factor = TariffFactor.objects.filter(attribute="usage", equals="commercial").first().multiplier
    assert factor == Decimal("1.4000")
    assert p_quotes.keys() == c_quotes.keys()
    for key, base in p_quotes.items():
        assert abs(c_quotes[key] - float(base) * float(factor)) <= 1, key  # même devis × 1,4 (arrondi)
    rc = Product.objects.filter(code="rc").first()
    assert c_quotes["rc" + rc.insurer.slug] == int(rc.base_premium * factor)  # 6 CV : seul l'usage joue


# --- Migration taxi → commercial --------------------------------------------------------------------

def test_migration_moves_taxi_to_commercial_without_repricing(customer_client, demo):
    policy_data, _ = buy(customer_client, plate="3030BB00", usage="commercial")
    policy = Policy.objects.get(pk=policy_data["id"])
    premium_before = policy.premium
    # État ancien : véhicule, devis et facteur tarifaire « taxi ».
    InsuredAsset.objects.filter(pk=policy.asset_id).update(attributes={"fiscal_power": 8, "usage": "taxi"})
    Quote.objects.filter(pk=policy.quote_id).update(attributes_snapshot={"fiscal_power": 8, "usage": "taxi"})
    product = policy.product
    TariffFactor.objects.create(product=product, attribute="usage", equals="taxi", multiplier=Decimal("1.8"))
    untouched = Quote.objects.create(customer=policy.customer, asset=policy.asset, product=product, premium=12345,
                                     tariff_version="x", attributes_snapshot={"usage": "personal"},
                                     expires_at=timezone.now() + timedelta(hours=1))

    import_module("apps.policies.migrations.0007_usage_taxi_vers_commercial").taxi_to_commercial(django_apps, None)

    policy.refresh_from_db()
    assert policy.asset.attributes["usage"] == "commercial"
    assert policy.quote.attributes_snapshot["usage"] == "commercial"
    assert policy.premium == premium_before  # police émise : montant inchangé, aucun recalcul
    assert not TariffFactor.objects.filter(attribute="usage", equals="taxi").exists()
    untouched.refresh_from_db()
    assert untouched.attributes_snapshot == {"usage": "personal"} and untouched.premium == 12345
