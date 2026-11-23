"""Rendu PDF de l'attestation : une page A4, français et arabe côte à côte.

Le PDF n'est qu'une présentation : l'authenticité repose sur le QR code, qui
porte le jeton signé (Ed25519) vérifiable en ligne ou hors ligne.
"""
import io
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from apps.policies.models import format_plate

FONTS = Path(__file__).parent / "fonts"

# Palette de l'app (globals.css)
INK = (11, 26, 20)
INK_2 = (38, 53, 47)
MUTED = (68, 82, 76)
LINE = (201, 212, 207)
BG = (233, 238, 235)
GREEN = (8, 96, 63)
DEEP = (6, 47, 34)
ON_DEEP = (207, 227, 217)
RED = (163, 38, 38)
RED_TINT = (251, 228, 228)

PAGE_W, MARGIN = 210, 14
CONTENT_W = PAGE_W - 2 * MARGIN

USAGE = {"personal": ("Personnel", "شخصي"), "commercial": ("Commercial", "تجاري")}


def _d(value: str | date) -> str:
    """Date neutre, lisible en français comme en arabe : 19/11/2026."""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d/%m/%Y")


def sigle(name: str) -> str:
    """Même règle que le composant InsurerLogo du frontend."""
    first = (name.split("(")[0].strip().split() or [name])[0]
    return first if first.isupper() and 2 <= len(first) <= 4 else first[:1].upper()


class AttestationPdf(FPDF):
    def __init__(self):
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(False)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        for family, file in (("sans", "NotoSans"), ("kufi", "NotoKufiArabic")):
            self.add_font(family, "", FONTS / f"{file}-Regular.ttf")
            self.add_font(family, "B", FONTS / f"{file}-Bold.ttf")
        # Noto Kufi n'a pas de lettres latines, Noto Sans pas d'arabe : chacune sert de secours à l'autre.
        self.set_fallback_fonts(["sans", "kufi"])
        self.set_text_shaping(True)  # liaisons et sens de lecture de l'arabe (HarfBuzz)

    def write_at(self, x, y, w, text, *, size=10, bold=False, color=INK, align="L", arabic=False, h=None):
        self.set_font("kufi" if arabic else "sans", "B" if bold else "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.cell(w, h or size * 0.5, text, align=align, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def lines_for(self, w, text, size, bold=False) -> int:
        self.set_font("sans", "B" if bold else "", size)
        return len(self.multi_cell(w, size * 0.48, text, dry_run=True, output="LINES"))


def render(attestation, *, specimen: bool) -> bytes:
    policy = attestation.policy
    customer, asset, product = policy.customer, policy.asset, policy.product
    insurer = product.insurer
    payload = attestation.payload
    attrs = asset.attributes

    pdf = AttestationPdf()
    pdf.set_title(f"Attestation {attestation.number}")
    pdf.set_author("Sanad")
    pdf.set_creator("Sanad")
    pdf.add_page()

    # --- En-tête -----------------------------------------------------------------
    pdf.set_fill_color(*DEEP)
    pdf.rect(0, 0, PAGE_W, 30, style="F")
    pdf.write_at(MARGIN, 9, 90, "Sanad", size=17, bold=True, color=(255, 255, 255))
    pdf.write_at(MARGIN, 18, 90, "Courtage d'assurance digital", size=8.5, color=ON_DEEP)
    pdf.write_at(PAGE_W - MARGIN - 90, 8, 90, "سند", size=17, bold=True, color=(255, 255, 255), align="R", arabic=True)
    pdf.write_at(PAGE_W - MARGIN - 90, 18, 90, "منصة رقمية لوساطة التأمين", size=8.5, color=ON_DEEP, align="R", arabic=True)

    y = 36
    if specimen:
        pdf.set_fill_color(*RED_TINT)
        pdf.rect(MARGIN, y, CONTENT_W, 11, style="F")
        pdf.write_at(MARGIN + 4, y + 3, 100, "SPÉCIMEN · Démonstration, sans valeur d'assurance", size=9, bold=True, color=RED)
        pdf.write_at(PAGE_W - MARGIN - 84, y + 2, 80, "نموذج تجريبي · بدون قيمة تأمينية", size=9, bold=True,
                     color=RED, align="R", arabic=True)
        # Filigrane en diagonale, derrière le contenu.
        with pdf.local_context(fill_opacity=0.10, text_color=RED):
            pdf.set_font("sans", "B", 80)
            cx, cy, word = PAGE_W / 2, 165, "SPÉCIMEN"
            with pdf.rotation(35, cx, cy):
                pdf.text(cx - pdf.get_string_width(word) / 2, cy + 10, word)
        y += 16

    # --- Titre et numéro ----------------------------------------------------------------
    pdf.write_at(MARGIN, y, 110, "ATTESTATION D'ASSURANCE AUTOMOBILE", size=13.5, bold=True)
    pdf.write_at(PAGE_W - MARGIN - 70, y - 1, 70, "شهادة تأمين السيارة", size=13.5, bold=True, align="R", arabic=True)
    y += 10
    pdf.set_fill_color(*INK)
    pdf.rect(MARGIN, y, CONTENT_W, 15, style="F")
    pdf.write_at(MARGIN + 5, y + 4.5, 30, "N°", size=10, color=ON_DEEP)
    pdf.write_at(MARGIN, y + 3.5, CONTENT_W, attestation.number, size=17, bold=True, color=(255, 255, 255), align="C")
    pdf.write_at(PAGE_W - MARGIN - 35, y + 3.5, 30, "الرقم", size=10, color=ON_DEEP, align="R", arabic=True)
    y += 22

    # --- Assureur --------------------------------------------------------------------------
    logo_size = 20
    pdf.set_draw_color(*LINE)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(MARGIN, y, logo_size, logo_size, style="DF", round_corners=True, corner_radius=2.5)
    logo = _logo_bytes(insurer)
    if logo:
        pdf.image(logo, x=MARGIN + 1.5, y=y + 1.5, w=logo_size - 3, h=logo_size - 3, keep_aspect_ratio=True)
    else:
        pdf.set_fill_color(*BG)
        pdf.rect(MARGIN, y, logo_size, logo_size, style="F", round_corners=True, corner_radius=2.5)
        pdf.write_at(MARGIN, y + 7.5, logo_size, sigle(insurer.name), size=11, bold=True, align="C")
    pdf.write_at(MARGIN + logo_size + 5, y + 2, 100, "Assureur", size=8.5, color=MUTED)
    pdf.write_at(MARGIN + logo_size + 5, y + 7, 110, insurer.name, size=13, bold=True)
    if insurer.legal_name and insurer.legal_name != insurer.name:
        pdf.write_at(MARGIN + logo_size + 5, y + 14, 120, insurer.legal_name, size=9, color=INK_2)
    pdf.write_at(PAGE_W - MARGIN - 40, y + 1, 40, "شركة التأمين", size=8.5, color=MUTED, align="R", arabic=True)
    y += logo_size + 6

    # --- Lignes bilingues : libellé FR | valeur | libellé AR ------------------------------------
    usage_fr, usage_ar = USAGE.get(attrs.get("usage", ""), (attrs.get("usage", ""), ""))
    vehicle = " · ".join(
        part for part in (
            str(attrs.get("make", "")).strip(),
            f"{attrs['fiscal_power']} CV" if attrs.get("fiscal_power") else "",
            f"{usage_fr} ({usage_ar})" if usage_ar else usage_fr,
        ) if part
    )
    rows = [
        ("Assuré", "المؤمَّن له", customer.full_name or "—", False),
        ("NNI", "الرقم الوطني", customer.nni or "—", False),
        ("Immatriculation", "رقم اللوحة", format_plate(payload["p"]), True),
        ("Véhicule", "السيارة", vehicle or "—", False),
        ("Formule", "الصيغة", product.name, True),
        ("Garanties", "الضمانات", ", ".join(product.coverages) or "—", False),
        ("Période de validité", "مدة السريان", f"du {_d(payload['f'])} au {_d(payload['t'])}", True),
        ("Émise le", "تاريخ الإصدار", _d(attestation.issued_at.date()), False),
    ]
    label_w, ar_w = 40, 36
    value_x, value_w = MARGIN + label_w, CONTENT_W - label_w - ar_w
    pdf.set_draw_color(*LINE)
    pdf.line(MARGIN, y, PAGE_W - MARGIN, y)
    for fr_label, ar_label, value, strong in rows:
        size = 11.5 if strong else 10.5
        n = pdf.lines_for(value_w, value, size, bold=strong)
        h = max(11, n * size * 0.48 + 5)
        pdf.write_at(MARGIN, y + 3.4, label_w, fr_label, size=8.5, color=MUTED)
        pdf.set_font("sans", "B" if strong else "", size)
        pdf.set_text_color(*INK)
        pdf.set_xy(value_x, y + 2.6)
        pdf.multi_cell(value_w, size * 0.48, value)
        pdf.write_at(PAGE_W - MARGIN - ar_w, y + 2.4, ar_w, ar_label, size=8.5, color=MUTED, align="R", arabic=True)
        y += h
        pdf.line(MARGIN, y, PAGE_W - MARGIN, y)

    # --- Vérification par QR -------------------------------------------------------------------
    from .services import qr_png  # import local : services importe ce module

    box_y, box_h, qr_size = max(y + 8, 214), 58, 46
    pdf.set_fill_color(*BG)
    pdf.rect(MARGIN, box_y, CONTENT_W, box_h, style="F", round_corners=True, corner_radius=4)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(MARGIN + 5, box_y + 6, qr_size, qr_size, style="F")
    pdf.image(io.BytesIO(qr_png(attestation)), x=MARGIN + 5, y=box_y + 6, w=qr_size, h=qr_size)
    tx, tw = MARGIN + qr_size + 11, CONTENT_W - qr_size - 16
    pdf.write_at(tx, box_y + 6, tw, "Vérifier cette attestation", size=11, bold=True)
    pdf.set_font("sans", "", 8.8)
    pdf.set_text_color(*INK_2)
    pdf.set_xy(tx, box_y + 12)
    pdf.multi_cell(tw, 4.2, "Scannez le QR code : la page de vérification confirme l'authenticité et la validité. "
                            "La signature numérique (Ed25519) se vérifie aussi sans réseau.")
    pdf.write_at(tx, box_y + 28, tw, "التحقق من هذه الشهادة", size=11, bold=True, align="R", arabic=True)
    pdf.set_font("kufi", "", 8.5)
    pdf.set_xy(tx, box_y + 35)
    pdf.multi_cell(tw, 4.6, "امسح رمز QR: تؤكد صفحة التحقق صحة الشهادة وسريانها. "
                            "يمكن التحقق من التوقيع الرقمي حتى دون اتصال.", align="R")
    pdf.write_at(tx, box_y + box_h - 7, tw, f"Clé de signature : {payload.get('k', '')}", size=7.5, color=MUTED)

    # --- Pied de page ------------------------------------------------------------------------------
    pdf.set_draw_color(*LINE)
    pdf.line(MARGIN, 280, PAGE_W - MARGIN, 280)
    pdf.write_at(MARGIN, 283, CONTENT_W / 2, "Seul le QR code fait foi. Document généré par Sanad.", size=7.5, color=MUTED)
    pdf.write_at(PAGE_W / 2, 282.5, CONTENT_W / 2, "رمز QR وحده هو المعتمد. وثيقة صادرة عن سند.", size=7.5,
                 color=MUTED, align="R", arabic=True)

    return bytes(pdf.output())


def _logo_bytes(insurer) -> io.BytesIO | None:
    """Logo officiel déposé par la compagnie ; None s'il manque ou est illisible (on affiche le sigle)."""
    if not insurer.logo:
        return None
    try:
        with insurer.logo.open("rb") as fh:
            return io.BytesIO(fh.read())
    except (OSError, ValueError):
        return None
