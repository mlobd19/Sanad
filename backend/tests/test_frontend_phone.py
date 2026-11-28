"""Numéros dans l'app : sans indicatif +222 (Sanad n'existe qu'en Mauritanie), alignés à droite en arabe.

Le frontend n'a pas d'outil de test : ces vérifications lisent ses sources (comme test_logo.py).
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def source(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding="utf-8")


def test_phone_is_shown_and_typed_without_country_code():
    fmt = source("lib", "format.ts")
    body = fmt.split("export function formatPhone", 1)[1].split("\n}", 1)[0]
    assert "+222" not in body  # « 36 00 00 01 »
    field = source("components", "PhoneInput.tsx")
    assert ">\n" not in field.split("return (", 1)[1].split("<input", 1)[0]  # plus de case « +222 » devant
    assert "+222\n" not in field and 'dir="ltr"' in field
    # L'indicatif reste ajouté à l'envoi : le numéro est enregistré sous la forme +222XXXXXXXX.
    assert "`+222${payer}`" in source("app", "(client)", "paiement", "[policyId]", "page.tsx")
    # Un numéro collé avec l'indicatif (+222 ou 00222) est ramené à ses 8 chiffres.
    assert re.search(r"replace\(/\^\(00\)\?222\(\?=\\d\{8\}\$\)/", fmt)


def test_left_to_right_fields_are_right_aligned_in_arabic():
    css = source("app", "globals.css")
    assert '[dir="rtl"] .input[dir="ltr"] { text-align: right; }' in css
    profile = source("app", "(client)", "profil", "page.tsx")
    assert 'id="phone" className="input" value={formatPhone(user.phone)} disabled dir="ltr"' in profile
    assert 'id="nni" className="input" value={nni} dir="ltr"' in profile


def test_country_code_typed_by_habit_is_dropped():
    field = source("components", "PhoneInput.tsx")
    assert '"222".startsWith(digits)' in field and "digits.slice(3, 11)" in field


def test_verified_nni_is_shown_but_not_editable():
    profile = source("app", "(client)", "profil", "page.tsx")
    assert '<input id="nni" className="input" value={user.nni} dir="ltr" disabled' in profile
    assert 'verified ? t("idNniLocked") : t("idCheckHint")' in profile and "{!verified && (" in profile
    assert ".input:disabled {" in source("app", "globals.css")
