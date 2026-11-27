"""Symbole Sanad « l'arche et l'élan », en SVG vectoriel pour l'en-tête du PDF.

Même tracé que frontend/components/Logo.tsx (viewBox 96, trait 7, extrémités arrondies,
point sable). Dans l'app, l'élan coupe l'arche par un masque SVG ; fpdf2 ne lit pas les
masques, mais il lit les tracés de découpe (`clipPath`). L'arche est donc découpée par
« tout le carré sauf l'élan épaissi à 15 » : un carré, et en sens inverse le contour de
l'élan (bords décalés de 7,5 de part et d'autre, bouts arrondis). Même résultat que le
masque, sans trait de la couleur du fond.
"""
import math
from functools import cache

ARCH = "M14 70A34 34 0 0 1 82 70"
ELAN = "M20 80C40 78 52 64 60 50C64 43 68 37 73 32"
# Les deux courbes de Bézier de l'élan (points de départ, de contrôle, d'arrivée).
ELAN_CURVES = (((20, 80), (40, 78), (52, 64), (60, 50)), ((60, 50), (64, 43), (68, 37), (73, 32)))
CUT = 7.5  # demi-largeur du trait de coupe (15 dans le masque de l'app)
SAND = "#f0a43a"


def _point(curve, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = curve
    u = 1 - t
    return (u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
            u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3)


def _tangent(curve, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = curve
    u = 1 - t
    dx = 3 * u * u * (x1 - x0) + 6 * u * t * (x2 - x1) + 3 * t * t * (x3 - x2)
    dy = 3 * u * u * (y1 - y0) + 6 * u * t * (y2 - y1) + 3 * t * t * (y3 - y2)
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def elan_outline(steps: int = 48) -> list[tuple[float, float]]:
    """Contour de l'élan épaissi à 2 × CUT, bouts arrondis : un polygone fermé."""
    samples = []  # (point, tangente) le long de l'élan
    for i, curve in enumerate(ELAN_CURVES):
        for k in range(0 if i == 0 else 1, steps + 1):
            t = k / steps
            samples.append((_point(curve, t), _tangent(curve, t)))
    left = [(x - ty * CUT, y + tx * CUT) for (x, y), (tx, ty) in samples]
    right = [(x + ty * CUT, y - tx * CUT) for (x, y), (tx, ty) in samples]

    def cap(center, tangent, start_angle):
        cx, cy = center
        base = math.atan2(tangent[1], tangent[0])
        return [(cx + CUT * math.cos(base + start_angle - math.pi * k / 16),
                 cy + CUT * math.sin(base + start_angle - math.pi * k / 16)) for k in range(1, 16)]

    (end, end_t), (start, start_t) = samples[-1], samples[0]
    return left + cap(end, end_t, math.pi / 2) + right[::-1] + cap(start, start_t, -math.pi / 2)


def _area(points) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])) / 2


@cache
def symbol_svg(color: str = "#ffffff") -> bytes:
    """Le symbole complet, trait `color`, point sable, prêt pour `FPDF.image`."""
    outline = elan_outline()
    square = [(0, 0), (96, 0), (96, 96), (0, 96)]
    if (_area(outline) > 0) == (_area(square) > 0):
        outline.reverse()  # sens inverse du carré : un trou, avec la règle « non nulle »
    hole = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in outline) + " Z"
    stroke = f'fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
        f'<defs><clipPath id="coupe"><path d="M0 0 L96 0 L96 96 L0 96 Z {hole}"/></clipPath></defs>'
        f'<path d="{ARCH}" clip-path="url(#coupe)" {stroke}/>'
        f'<path d="{ELAN}" {stroke}/>'
        f'<circle cx="80" cy="24" r="7" fill="{SAND}"/>'
        "</svg>"
    ).encode()
