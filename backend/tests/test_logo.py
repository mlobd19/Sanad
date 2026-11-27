"""Logo « l'arche et l'élan » : même tracé partout, coupure par masque ou découpe, jamais par un trait du fond."""
import json
import re
from pathlib import Path

from django.test import Client

from apps.attestations.logo import ARCH, ELAN, _area, elan_outline, symbol_svg

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
KHAIMA = "M12 74C28 66 36 44 48 16"  # ancien symbole : ne doit plus apparaître nulle part


def test_pdf_symbol_cuts_the_arch_with_a_clip_path_not_a_background_stroke():
    svg = symbol_svg("#ffffff").decode()
    assert f'd="{ARCH}" clip-path="url(#coupe)"' in svg and f'd="{ELAN}"' in svg
    assert 'r="7" fill="#f0a43a"' in svg  # point sable
    strokes = set(re.findall(r'stroke="([^"]+)"', svg))
    assert strokes == {"#ffffff"}  # aucun trait couleur du fond (vert profond) pour simuler la coupure
    assert "stroke-width=\"15\"" not in svg


def test_cut_outline_is_the_elan_thickened_to_15_with_opposite_winding():
    outline = elan_outline()
    # Chaque point du contour est à 7,5 de l'élan (le trait de 15 du masque de l'app).
    from apps.attestations.logo import ELAN_CURVES, _point

    samples = [_point(c, k / 200) for c in ELAN_CURVES for k in range(201)]
    for x, y in outline[::7]:
        nearest = min(((x - px) ** 2 + (y - py) ** 2) ** 0.5 for px, py in samples)
        assert abs(nearest - 7.5) < 0.2
    square = [(0, 0), (96, 0), (96, 96), (0, 96)]
    svg = symbol_svg("#ffffff").decode()
    hole = [tuple(map(float, p.split())) for p in re.search(r"Z M(.*?) Z", svg).group(1).split(" L")]
    assert (_area(hole) > 0) != (_area(square) > 0)  # sens inverse : un trou dans la découpe


def test_verification_page_and_backoffice_use_the_arch_with_a_mask():
    for template in ("apps/attestations/templates/attestations/verify.html",
                     "apps/backoffice/templates/admin/base_site.html"):
        html = (BACKEND / template).read_text()
        assert KHAIMA not in html
        mask = re.search(r'<mask id="([^"]+)">', html).group(1)
        assert f'd="{ARCH}" mask="url(#{mask})"' in html and f'd="{ELAN}" stroke="black" stroke-width="15"' in html


def test_backoffice_login_shows_the_new_logo():
    html = Client().get("/admin/login/").content.decode()
    assert ARCH in html and KHAIMA not in html


def test_app_icons_and_manifest():
    manifest = json.loads((FRONTEND / "public/manifest.webmanifest").read_text())
    icons = {(i["src"], i["purpose"]) for i in manifest["icons"]}
    assert {("/icon-192.png", "any"), ("/icon-512.png", "any"), ("/icon-maskable-512.png", "maskable")} <= icons
    for src, _ in icons:
        assert (FRONTEND / "public" / src.lstrip("/")).exists(), src
    for name in ("icon.svg", "icon-maskable.svg"):
        svg = (FRONTEND / "public" / name).read_text()
        assert ARCH in svg and ELAN in svg and "#08603f" in svg and "#f0a43a" in svg and KHAIMA not in svg


def test_old_khaima_symbol_is_gone_everywhere():
    sources = [p for d in ("frontend/app", "frontend/components", "frontend/public", "backend/apps")
               for p in (ROOT / d).rglob("*") if p.suffix in {".tsx", ".ts", ".svg", ".html", ".py", ".css"}]
    assert sources
    leftovers = [str(p) for p in sources if KHAIMA in p.read_text(errors="ignore") or "KhaimaMark" in p.read_text(errors="ignore")]
    assert leftovers == []
