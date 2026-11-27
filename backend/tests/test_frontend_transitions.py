"""Transitions entre écrans de l'app client : les règles restent tenues dans le code du frontend.

Le frontend n'a pas d'outil de test : ces vérifications lisent ses sources (comme test_logo.py).
"""
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CLIENT = FRONTEND / "app" / "(client)"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def client_pages() -> list[Path]:
    return sorted(CLIENT.rglob("page.tsx"))


def test_client_screens_share_one_layout_with_fixed_bars():
    assert (CLIENT / "layout.tsx").exists()
    chrome = source(FRONTEND / "components" / "ClientChrome.tsx")
    assert "<TopBar" in chrome and "<BottomNav" in chrome and "<ViewTransition key={pathname}" in chrome
    for page in client_pages():
        text = source(page)
        # Barres rendues une seule fois par le layout, jamais par un écran.
        assert "<TopBar" not in text and "<BottomNav" not in text, page
    shell = source(FRONTEND / "components" / "Shell.tsx")
    assert 'viewTransitionName: "sn-topbar"' in shell and 'viewTransitionName: "sn-bottomnav"' in shell


def test_every_client_screen_is_described_in_the_screen_table():
    screens = source(FRONTEND / "lib" / "screens.ts")
    patterns = [re.compile(p) for p in re.findall(r"pattern: /(.+?)/,", screens)]
    for page in client_pages():
        route = "/" + "/".join(page.relative_to(CLIENT).parent.parts)
        url = re.sub(r"\[[^\]]+\]", "1", route).replace("//", "/").rstrip("/") or "/"
        assert any(p.search(url.replace("\\", "")) for p in patterns), f"{url} absent de lib/screens.ts"


def test_navigation_uses_the_directional_link_and_push_only_after_an_action():
    files = client_pages() + [FRONTEND / "app" / "entreprise" / "page.tsx",
                              FRONTEND / "components" / "ClaimsSection.tsx", FRONTEND / "components" / "Shell.tsx"]
    for path in files:
        text = source(path)
        assert 'from "next/link"' not in text, f"{path} : utiliser Link de components/NavLink"
        assert "router.push(" not in text, f"{path} : useNav().push après une action"
    for page in client_pages():
        assert "<Loading" not in source(page), f"{page} : squelette au lieu d'un indicateur plein écran"


def test_transition_types_and_css():
    transitions = source(FRONTEND / "lib" / "transitions.ts")
    for kind in ("nav-forward", "nav-back", "nav-tab"):
        assert f'"{kind}"' in transitions
    css = source(FRONTEND / "app" / "globals.css")
    # Glissement vers la gauche en avançant, inversé en arabe ; durée et courbe ; barres fixes.
    assert "--nav-duration: 220ms" in css and "ease-out both nav-leave" in css
    assert 'html[dir="rtl"]::view-transition-old(.nav-forward)' in css
    assert "::view-transition-new(sn-topbar), ::view-transition-new(sn-bottomnav) { animation: none; }" in css
    reduced = css[css.index("@media (prefers-reduced-motion: reduce) {\n  ::view-transition"):]
    assert "animation: none !important" in reduced
    # Les onglets de l'espace entreprise passent en fondu par addTransitionType.
    company = source(FRONTEND / "app" / "entreprise" / "page.tsx")
    assert 'addTransitionType("nav-tab")' in company and "<ViewTransition key={tab}" in company


def test_cached_data_is_cleared_with_the_session():
    api = source(FRONTEND / "lib" / "api.ts")
    set_token = api[api.index("export function setToken"):]
    assert "cache.clear()" in set_token.split("\n}")[0]
