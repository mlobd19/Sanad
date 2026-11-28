"""Code PIN dans l'app : pavé virtuel aux touches mélangées, écrans du code, textes FR + AR.

Le frontend n'a pas d'outil de test : ces vérifications lisent ses sources (comme test_logo.py).
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def source(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding="utf-8")


PAD = ("components", "SecurePinPad.tsx")
SCREENS = [("app", "connexion", "code", "page.tsx"), ("app", "(client)", "profil", "code", "page.tsx")]


def test_pad_never_uses_an_input_or_the_phone_keyboard():
    for parts in [PAD, *SCREENS, ("lib", "pin.ts")]:
        code = source(*parts)
        assert not re.search(r"<input[ >]", code) and "inputMode" not in code
        assert "localStorage" not in code and "sessionStorage" not in code  # jamais dans le navigateur
        assert "console." not in code  # jamais dans les journaux


def test_digits_are_shuffled_with_crypto_and_fisher_yates():
    lib = source("lib", "pin.ts")
    assert "crypto.getRandomValues" in lib and "Math.random" not in lib
    assert "for (let i = digits.length - 1; i > 0; i--)" in lib and "randomBelow(i + 1)" in lib
    pad = source(*PAD)
    assert "setDigits(shuffledDigits())" in pad  # à chaque affichage (montage du pavé)
    # « Effacer » et la case vide gardent leur place, les 10 chiffres prennent les autres cases.
    assert '[...digits.slice(0, 9), "empty", digits[9], "erase"]' in pad
    for screen in SCREENS:
        assert "key={round}" in source(*screen)  # nouvelle étape ou erreur : saisie vidée, chiffres remélangés


def test_pad_is_accessible_and_reveals_nothing():
    pad = source(*PAD)
    assert '<button key={`k${i}`} type="button"' in pad and "aria-label={cell || undefined}" in pad
    assert 'aria-label={t("pinEraseLabel")}' in pad and 'role="group"' in pad
    assert 'className="pin-dots" aria-hidden="true"' in pad and 'aria-live="polite"' in pad
    assert "if (entered.current.length === PIN_LENGTH) onComplete(entered.current)" in pad  # 4e chiffre
    assert "navigator.vibrate?.(10)" in pad  # bref retour tactile
    css = source("app", "globals.css")
    rule = css.split(".pinpad button {", 1)[1].split("}", 1)[0]
    assert "-webkit-tap-highlight-color: transparent" in rule and "transition: none" in rule
    assert int(re.search(r"min-height: (\d+)px", rule).group(1)) >= 56
    assert ".pinpad button:active, .pinpad button:hover { background: var(--bg); color: var(--ink); }" in css
    small = css.split("@media (max-height: 760px) {\n  .pin-head", 1)[1].split("\n}", 1)[0]
    assert int(re.search(r"\.pinpad button \{ min-height: (\d+)px", small).group(1)) >= 56
    assert not re.search(r"#[0-9a-fA-F]{3,6}", css.split("/* --- Code PIN", 1)[1].replace("color: #fff", ""))


def test_pin_texts_exist_in_french_and_arabic():
    i18n = source("lib", "i18n.tsx")
    for key in ["pinChooseTitle", "pinConfirmTitle", "pinEnterTitle", "pinForgot", "pinTooSimple", "pinWrong",
                "pinBlocked", "pinChangeTitle", "pinOldTitle", "pinNewTitle", "pinErase", "pinEraseLabel"]:
        assert i18n.count(f"  {key}: ") == 2, key
    assert 'pinTooSimple: "Code trop simple, choisissez-en un autre"' in i18n
    assert ('pinWrong: "one: Code incorrect, il vous reste {n} essai | other: Code incorrect, il vous reste {n} essais"'
            in i18n)
    assert not re.search(r"\w\(s\)", i18n)  # jamais « essai(s) »


def test_customers_reach_the_pin_screen_after_sms_and_when_locked():
    login = source("app", "connexion", "page.tsx")
    assert "router.replace(pinUrl())" in login and '"pinBlocked"' in login
    api = source("lib", "api.ts")
    assert 'code === "pin_required" || code === "pin_setup"' in api
    assert "window.location.href = pinUrl(path + window.location.search)" in api
    pin_screen = source(*SCREENS[0])
    assert 'onClick={() => logout(router)}' in pin_screen  # « Code oublié ? » : retour au code SMS
    assert '{ id: "pinChange", depth: 1, title: "pinChangeTitle"' in source("lib", "screens.ts")
    assert 'href="/profil/code"' in source("app", "(client)", "profil", "page.tsx")
