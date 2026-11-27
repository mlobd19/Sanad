"""Accueil client : contrats en carrousel horizontal, « Souscrire une assurance » visible sans défiler.

Le frontend n'a pas d'outil de test : ces vérifications lisent ses sources (comme test_logo.py).
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def source(*parts: str) -> str:
    return FRONTEND.joinpath(*parts).read_text(encoding="utf-8")


def test_contracts_are_an_accessible_native_carousel():
    home = source("app", "(client)", "page.tsx")
    assert 'role="list"' in home and 'aria-label={t("myContracts")}' in home and 'role="listitem"' in home
    assert "<ContractCarousel policies={orderContracts(current)} />" in home
    # Défilement natif en CSS, sans bibliothèque ni défilement automatique.
    assert "setInterval(update" in home and home.count("setInterval") == 1  # seule minuterie : la salutation
    css = source("app", "globals.css")
    carousel = re.search(r"^\.carousel \{[^}]*\}", css, re.M).group(0)
    for rule in ("overflow-x: auto", "scroll-snap-type: x mandatory", "scrollbar-width: none"):
        assert rule in carousel
    assert "scroll-snap-align: start" in css and ".carousel::-webkit-scrollbar { display: none; }" in css
    # Un seul contrat : pleine largeur, ni points ni « Tout voir ».
    assert ".carousel.single .carousel-item { flex-basis: 100%; }" in css
    assert "{several && (" in home and 't("seeAll"' in home and 'href="/contrats"' in home


def test_contracts_needing_an_action_come_first():
    home = source("app", "(client)", "page.tsx")
    rank = home[home.index("function actionRank"):home.index("function orderContracts")]
    assert rank.index('"paid"') < rank.index('"draft"') < rank.index("<= 30")
    assert "a.ends_on.localeCompare(b.ends_on)" in home


def test_spacing_and_texts():
    css = source("app", "globals.css")
    assert "--section-gap: 37px;" in css and ".home { gap: var(--section-gap); }" in css
    # 64 px sous le texte du bandeau, chevauchement de 56 px, 16 px de marge : 24 px.
    assert ".overlap { margin-top: -56px; }" in css and "padding: 20px 20px 64px" in css
    i18n = source("lib", "i18n.tsx")
    assert i18n.count("seeAll:") == 2 and "Tout voir ({count})" in i18n and "عرض الكل ({count})" in i18n


def test_home_skeleton_has_the_carousel_shape():
    skeletons = source("components", "Skeletons.tsx")
    home = skeletons[skeletons.index("export function HomeContractsSkeleton"):]
    assert home.count('className="carousel-item"') == 2 and 'gap: "var(--section-gap)"' in home
