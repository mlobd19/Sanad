"""Textes de l'app qui dépendent d'un nombre : singulier et pluriel accordés, jamais « (s) ».

« 1 contrat actif », « 2 contrats actifs » ; en arabe, les six formes (zero, one, two, few, many,
other). Le frontend n'a pas d'outil de test : ces vérifications lisent lib/i18n.tsx.
"""
import re
from pathlib import Path

I18N = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n.tsx"


def dictionaries() -> tuple[dict[str, str], dict[str, str]]:
    text = I18N.read_text(encoding="utf-8")
    split = text.index("const ar: Record<Key, string>")
    entry = re.compile(r'^  (\w+): "((?:[^"\\]|\\.)*)",$', re.M)
    return dict(entry.findall(text[:split])), dict(entry.findall(text[split:]))


def forms(value: str) -> dict[str, str]:
    return {part.split(":", 1)[0].strip(): part.split(":", 1)[1].strip() for part in value.split("|")}


def test_no_text_writes_a_plural_with_parentheses():
    fr, ar = dictionaries()
    assert fr and ar
    assert [key for key, value in fr.items() if "(s)" in value] == []


def test_counted_texts_agree_in_french_and_arabic():
    fr, ar = dictionaries()
    plural_keys = [key for key, value in fr.items() if "|" in value]
    assert "activeCount" in plural_keys
    for key in plural_keys:
        fr_forms = forms(fr[key])
        assert {"one", "other"} <= set(fr_forms), key
        assert "|" in ar[key], f"{key} : formes arabes manquantes"
        ar_forms = forms(ar[key])
        assert {"one", "two", "few", "many", "other"} <= set(ar_forms), key
        assert set(fr_forms) | set(ar_forms) <= {"zero", "one", "two", "few", "many", "other"}, key
    assert forms(fr["activeCount"]) == {"one": "{count} contrat actif", "other": "{count} contrats actifs"}
