"""Assurance voyage côté app : parcours, textes FR + AR, mêmes écrans et composants que l'auto.

Le frontend n'a pas d'outil de test : ces vérifications lisent ses sources (comme test_logo.py).
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def source(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding="utf-8")


def test_travel_tile_is_available_and_opens_the_journey():
    home = source("app", "(client)", "page.tsx")
    assert '{ key: "travel", icon: "plane", href: "/voyage" }' in home
    assert "function TripCard" in home  # carrousel : avion, destination, dates, voyageurs


def test_travel_screens_follow_the_shared_navigation():
    screens = source("lib", "screens.ts")
    for path in (r"\/voyage$", r"\/voyage\/([^/]+)\/voyageurs$", r"\/voyage\/([^/]+)\/offres$"):
        assert path.replace("\\", "") in screens.replace("\\", "")
    assert 'flow: "travel"' in screens and "travelStep: 3" in screens  # paiement commun : étape du voyage
    shell = source("components", "Shell.tsx")
    assert '[t("stepTrip"), t("stepTravelers"), t("stepOffer"), t("stepPay")]' in shell


def test_travel_texts_exist_in_french_and_arabic():
    i18n = source("lib", "i18n.tsx")
    keys = re.findall(r"^  (travel\w+|limit_\w+|claimKind_(?:medical|repatriation|baggage|delay)): ", i18n, re.M)
    assert keys and all(keys.count(k) == 2 for k in set(keys)), "texte voyage sans traduction"
    # Messages d'eID d'un voyageur : les mêmes que le profil.
    assert 'travelErr_not_found: "Ce NNI est introuvable. Vérifiez les chiffres saisis et réessayez."' in i18n
    assert 'travelErr_unavailable: "Service indisponible, réessayez dans quelques minutes."' in i18n


def test_company_missions_reuse_the_app_components():
    company = source("app", "entreprise", "page.tsx")
    assert '{ id: "missions", label: "tabMissions" }' in company
    for component in ("<TripForm", "<TravelersEditor", "<TravelOffers"):
        assert component in company
    assert 'base="company/"' in company and "max={50}" in company


def test_claim_form_reminds_to_call_assistance_first():
    form = source("components", "ClaimForm.tsx")
    assert 't("claimAssistanceFirst"' in form and "<AssistanceLink" in form
    assert 'const TRAVEL_KINDS: ClaimKind[] = ["medical", "repatriation", "baggage", "delay", "theft", "other"]' in form
