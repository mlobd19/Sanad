"""Attestation d'assurance voyage : une page A4 par voyageur, en français, arabe et anglais.

L'anglais est lu par les consulats (visa Schengen) et les hôpitaux à l'étranger. Même en-tête,
même QR et mêmes règles que l'attestation auto (pdf.py) : jamais de prime, « SPÉCIMEN » tant
qu'aucun partenariat n'est signé.
"""
import io

from apps.policies.travel import country_names

from .logo import symbol_svg
from .pdf import (BG, CONTENT_W, DEEP, GREEN, INK, INK_2, LINE, MARGIN, MUTED, ON_DEEP, PAGE_W, RED, RED_TINT,
                  AttestationPdf, _d, _logo_bytes, sigle)

# Garanties comparées (Product.limits) : libellés français, anglais, arabe.
LIMITS = [
    ("medical", "Frais médicaux et hospitalisation", "Medical expenses and hospitalisation", "المصاريف الطبية والاستشفاء"),
    ("repatriation", "Rapatriement", "Repatriation", "الإعادة إلى الوطن"),
    ("baggage", "Bagages", "Baggage", "الأمتعة"),
    ("delay", "Retard de vol", "Flight delay", "تأخر الرحلة"),
    ("liability", "Responsabilité civile vie privée", "Personal liability", "المسؤولية المدنية الخاصة"),
]


def euros(value) -> str:
    """« 30 000 € » ; null = frais réels."""
    if value is None:
        return "Frais réels · Actual costs"
    return f"{int(value):,} €".replace(",", " ")


def render(attestation, *, specimen: bool) -> bytes:
    policy = attestation.policy
    traveler, trip = attestation.traveler, policy.asset.trip
    product = policy.product
    insurer = product.insurer
    payload = attestation.payload
    limits = product.limits or {}
    white = (255, 255, 255)

    pdf = AttestationPdf()
    pdf.set_title(f"Attestation {attestation.number}")
    pdf.set_author("Sanad")
    pdf.set_creator("Sanad")
    pdf.add_page()

    # --- En-tête (identique à l'auto) ---------------------------------------------------------------
    pdf.set_fill_color(*DEEP)
    pdf.rect(0, 0, PAGE_W, 26, style="F")
    pdf.image(io.BytesIO(symbol_svg("#ffffff")), x=MARGIN, y=4, w=17, h=17, alt_text="Logo Sanad")
    pdf.write_at(MARGIN + 21, 7, 90, "Sanad", size=16, bold=True, color=white)
    pdf.write_at(MARGIN + 21, 15.5, 90, "Courtage d'assurance digital", size=8, color=ON_DEEP)
    pdf.write_at(PAGE_W - MARGIN - 90, 6, 90, "سند", size=16, bold=True, color=white, align="R", arabic=True)
    pdf.write_at(PAGE_W - MARGIN - 90, 15.5, 90, "منصة رقمية لوساطة التأمين", size=8, color=ON_DEEP, align="R", arabic=True)

    y = 30
    if specimen:
        pdf.set_fill_color(*RED_TINT)
        pdf.rect(MARGIN, y, CONTENT_W, 10, style="F")
        pdf.write_at(MARGIN + 3, y + 2.6, 120, "SPÉCIMEN · Démonstration, sans valeur d'assurance · Specimen, no insurance value",
                     size=8, bold=True, color=RED)
        pdf.write_at(PAGE_W - MARGIN - 58, y + 1.8, 55, "نموذج تجريبي · بدون قيمة تأمينية", size=8, bold=True,
                     color=RED, align="R", arabic=True)
        with pdf.local_context(fill_opacity=0.10, text_color=RED):
            pdf.set_font("sans", "B", 80)
            cx, cy, word = PAGE_W / 2, 160, "SPÉCIMEN"
            with pdf.rotation(35, cx, cy):
                pdf.text(cx - pdf.get_string_width(word) / 2, cy + 10, word)
        y += 13

    # --- Titre et numéro ------------------------------------------------------------------------------
    pdf.write_at(MARGIN, y, 120, "ATTESTATION D'ASSURANCE VOYAGE", size=13, bold=True)
    pdf.write_at(MARGIN, y + 6.5, 120, "TRAVEL INSURANCE CERTIFICATE", size=10, bold=True, color=INK_2)
    pdf.write_at(PAGE_W - MARGIN - 70, y, 70, "شهادة تأمين السفر", size=13, bold=True, align="R", arabic=True)
    y += 14
    pdf.set_fill_color(*INK)
    pdf.rect(MARGIN, y, CONTENT_W, 12, style="F")
    pdf.write_at(MARGIN + 4, y + 3.6, 30, "N° · No.", size=9, color=ON_DEEP)
    pdf.write_at(MARGIN, y + 2.6, CONTENT_W, attestation.number, size=15, bold=True, color=white, align="C")
    pdf.write_at(PAGE_W - MARGIN - 30, y + 2.6, 26, "الرقم", size=9, color=ON_DEEP, align="R", arabic=True)
    y += 16

    # --- Assureur et assistance 24 h/24 -----------------------------------------------------------------
    logo_size = 16
    pdf.set_draw_color(*LINE)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(MARGIN, y, logo_size, logo_size, style="DF", round_corners=True, corner_radius=2)
    logo = _logo_bytes(insurer)
    if logo:
        pdf.image(logo, x=MARGIN + 1.2, y=y + 1.2, w=logo_size - 2.4, h=logo_size - 2.4, keep_aspect_ratio=True)
    else:
        pdf.set_fill_color(*BG)
        pdf.rect(MARGIN, y, logo_size, logo_size, style="F", round_corners=True, corner_radius=2)
        pdf.write_at(MARGIN, y + 5.8, logo_size, sigle(insurer.name), size=9.5, bold=True, align="C")
    pdf.write_at(MARGIN + logo_size + 4, y + 1, 70, "Assureur · Insurer", size=8, color=MUTED)
    pdf.write_at(MARGIN + logo_size + 4, y + 6, 75, insurer.name, size=12, bold=True)
    if insurer.legal_name and insurer.legal_name != insurer.name:
        pdf.write_at(MARGIN + logo_size + 4, y + 11.5, 75, insurer.legal_name, size=7.5, color=INK_2)
    # Encadré vert : le numéro à appeler en urgence, avant toute dépense.
    box_x, box_w = MARGIN + 98, CONTENT_W - 98
    pdf.set_fill_color(*GREEN)
    pdf.rect(box_x, y - 1, box_w, logo_size + 2, style="F", round_corners=True, corner_radius=2.5)
    pdf.write_at(box_x + 3, y + 0.6, box_w - 6, "Assistance 24 h/24 · 24/7 assistance", size=7.5, color=white)
    pdf.write_at(box_x + 3, y + 5.2, box_w - 6, insurer.assistance_phone or "—", size=12.5, bold=True, color=white)
    pdf.write_at(box_x + 3, y + 10.4, box_w - 6, "المساعدة على مدار الساعة", size=7.5, color=white, align="R", arabic=True)
    y += logo_size + 5

    # --- Voyageur et voyage : libellé FR / EN | valeur | libellé AR -------------------------------------
    days = trip.days
    rows = [
        ("Voyageur", "Traveller (as in passport)", "المسافر", traveler.full_name, traveler.full_name_ar, True),
        ("N° de passeport", "Passport No.", "رقم جواز السفر", traveler.passport_number, "", True),
        ("Date de naissance", "Date of birth", "تاريخ الميلاد", _d(traveler.birth_date), "", False),
        ("NNI", "National ID No.", "الرقم الوطني", traveler.nni, "", False),
        ("Destination(s)", "Destination(s)", "الوجهة",
         f"{country_names(payload['d'], 'fr')}\n{country_names(payload['d'], 'en')}", country_names(payload["d"], "ar"), True),
        ("Validité", "Period of cover", "مدة السريان",
         f"du {_d(payload['f'])} au {_d(payload['t'])} ({days} j)\nfrom {_d(payload['f'])} to {_d(payload['t'])} ({days} days)",
         "", True),
        # La formule unique s'appelle « Monde entier » : c'est aussi la zone couverte.
        ("Zone couverte", "Territorial scope", "النطاق",
         "Monde entier, espace Schengen compris\nWorldwide, including the Schengen area", "جميع دول العالم، بما فيها منطقة شنغن", False),
        ("Émise le", "Issued on", "تاريخ الإصدار", _d(attestation.issued_at.date()), "", False),
    ]
    label_w, ar_w = 40, 40
    value_x, value_w = MARGIN + label_w, CONTENT_W - label_w - ar_w
    pdf.set_draw_color(*LINE)
    pdf.line(MARGIN, y, PAGE_W - MARGIN, y)
    for fr_label, en_label, ar_label, value, ar_value, strong in rows:
        size = 10 if strong else 9.2
        lines = sum(pdf.lines_for(value_w, part, size, bold=strong) for part in value.split("\n"))
        h = max(9.0, lines * size * 0.46 + 3.6)
        pdf.write_at(MARGIN, y + 1.8, label_w, fr_label, size=7.8, color=MUTED)
        pdf.write_at(MARGIN, y + 5.4, label_w, en_label, size=6.6, color=MUTED)
        pdf.set_font("sans", "B" if strong else "", size)
        pdf.set_text_color(*INK)
        pdf.set_xy(value_x, y + 2)
        pdf.multi_cell(value_w, size * 0.46, value)
        pdf.write_at(PAGE_W - MARGIN - ar_w, y + 1.2, ar_w, ar_label, size=7.8, color=MUTED, align="R", arabic=True)
        if ar_value:
            pdf.set_font("kufi", "", 8.5)
            pdf.set_text_color(*INK)
            pdf.set_xy(PAGE_W - MARGIN - ar_w, y + 5.2)
            pdf.multi_cell(ar_w, 4.2, ar_value, align="R")
            h = max(h, pdf.get_y() - y + 1.5)
        y += h
        pdf.line(MARGIN, y, PAGE_W - MARGIN, y)

    # --- Garanties et plafonds ------------------------------------------------------------------------
    y += 4
    pdf.write_at(MARGIN, y, 110, "Garanties et plafonds · Covers and limits", size=10, bold=True)
    pdf.write_at(PAGE_W - MARGIN - 60, y - 0.8, 60, "الضمانات والسقوف", size=10, bold=True, align="R", arabic=True)
    y += 6.5
    for i, (code, fr, en, ar) in enumerate(LIMITS):
        if i % 2 == 0:
            pdf.set_fill_color(*BG)
            pdf.rect(MARGIN, y, CONTENT_W, 7, style="F")
        pdf.write_at(MARGIN + 2, y + 1.4, 100, f"{fr} · {en}", size=8.3, color=INK)
        pdf.write_at(MARGIN + 100, y + 1.3, 40, euros(limits.get(code)), size=9, bold=True, align="R")
        pdf.write_at(PAGE_W - MARGIN - 44, y + 0.6, 42, ar, size=8, color=INK_2, align="R", arabic=True)
        y += 7

    # Mention pour les consulats (visa Schengen) : frais médicaux d'au moins 30 000 €.
    medical = euros(limits.get("medical"))
    y += 3
    pdf.set_font("sans", "", 8)
    pdf.set_text_color(*INK_2)
    pdf.set_xy(MARGIN, y)
    pdf.multi_cell(CONTENT_W, 3.8,
                   f"Valable dans tous les pays de l'espace Schengen : frais médicaux, hospitalisation et rapatriement "
                   f"couverts jusqu'à {medical}. · Valid in all Schengen States: medical expenses, hospitalisation and "
                   f"repatriation covered up to {medical}.")
    pdf.set_font("kufi", "", 7.8)
    pdf.set_xy(MARGIN, pdf.get_y() + 0.6)
    pdf.multi_cell(CONTENT_W, 4.2, f"صالحة في جميع دول منطقة شنغن: المصاريف الطبية والاستشفاء والإعادة إلى الوطن "
                                   f"مغطاة حتى {medical}.", align="R")
    y = pdf.get_y()

    # --- Vérification par QR ----------------------------------------------------------------------------
    from .services import qr_png  # import local : services importe ce module

    box_h, qr_size = 36, 30
    box_y = min(max(y + 4, 240), 280 - box_h - 2)  # jamais sur le pied de page
    pdf.set_fill_color(*BG)
    pdf.rect(MARGIN, box_y, CONTENT_W, box_h, style="F", round_corners=True, corner_radius=3)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(MARGIN + 3, box_y + 3, qr_size, qr_size, style="F")
    pdf.image(io.BytesIO(qr_png(attestation)), x=MARGIN + 3, y=box_y + 3, w=qr_size, h=qr_size)
    tx, tw = MARGIN + qr_size + 8, CONTENT_W - qr_size - 11
    pdf.write_at(tx, box_y + 3, tw, "Vérifier cette attestation · Verify this certificate", size=9.5, bold=True)
    pdf.set_font("sans", "", 7.6)
    pdf.set_text_color(*INK_2)
    pdf.set_xy(tx, box_y + 8.4)
    pdf.multi_cell(tw, 3.5, "Scannez le QR code : la page de vérification confirme l'authenticité et la validité. "
                            "Scan the QR code: the verification page confirms authenticity and validity.")
    pdf.write_at(tx, box_y + 18, tw, "امسح رمز QR للتحقق من صحة الشهادة وسريانها", size=8, align="R", arabic=True)
    pdf.write_at(tx, box_y + box_h - 6, tw, f"Clé de signature · Signing key : {payload.get('k', '')}", size=6.8, color=MUTED)

    # --- Pied de page -------------------------------------------------------------------------------------
    pdf.set_draw_color(*LINE)
    pdf.line(MARGIN, 282, PAGE_W - MARGIN, 282)
    pdf.write_at(MARGIN, 284.5, CONTENT_W * 0.62, "Seul le QR code fait foi · Only the QR code is authoritative · Sanad",
                 size=7, color=MUTED)
    pdf.write_at(PAGE_W / 2, 284, CONTENT_W / 2, "رمز QR وحده هو المعتمد · سند", size=7, color=MUTED, align="R", arabic=True)

    return bytes(pdf.output())
