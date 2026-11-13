from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from benutzer_export_utils import name_aufteilen


def _text(wert, fallback="-"):
    wert = str(wert or "").strip()
    return escape(wert or fallback)


def benutzerliste_pdf_erstellen(benutzer, filterdaten=None):
    """Erzeugt eine druckfreundliche A4-PDF für die gefilterte Benutzerliste."""
    try:
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as fehler:
        raise RuntimeError(
            "Für den PDF-Export fehlt die Abhängigkeit reportlab."
        ) from fehler

    # Bitstream Vera wird mit ReportLab ausgeliefert. Durch das Einbetten
    # bleibt die Typografie unabhängig vom Betriebssystem sauber und lesbar.
    schrift_normal = "ExportSans"
    schrift_fett = "ExportSans-Bold"
    reportlab_schriftpfad = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(
        TTFont(schrift_normal, reportlab_schriftpfad / "Vera.ttf")
    )
    pdfmetrics.registerFont(
        TTFont(schrift_fett, reportlab_schriftpfad / "VeraBd.ttf")
    )

    filterdaten = filterdaten or {}
    puffer = BytesIO()
    rand = 17 * mm
    doc = SimpleDocTemplate(
        puffer,
        pagesize=landscape(A4),
        rightMargin=rand,
        leftMargin=rand,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title="Benutzerliste",
        author="Lizenzmanagement",
    )

    styles = getSampleStyleSheet()
    titel = ParagraphStyle(
        "ExportTitel",
        parent=styles["Title"],
        fontName=schrift_fett,
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#1f2a20"),
        spaceAfter=4,
    )
    untertitel = ParagraphStyle(
        "ExportUntertitel",
        parent=styles["Normal"],
        fontName=schrift_normal,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#647064"),
        spaceAfter=10,
    )
    filterstil = ParagraphStyle(
        "ExportFilter",
        parent=styles["Normal"],
        fontName=schrift_normal,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#405143"),
        backColor=colors.HexColor("#eff6ef"),
        borderColor=colors.HexColor("#d4e5d4"),
        borderWidth=0.6,
        borderPadding=7,
        spaceAfter=14,
    )
    zellenstil = ParagraphStyle(
        "ExportZelle",
        parent=styles["Normal"],
        fontName=schrift_normal,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#263128"),
    )
    kopfstil = ParagraphStyle(
        "ExportKopf",
        parent=zellenstil,
        fontName=schrift_fett,
        textColor=colors.white,
    )
    rechtsstil = ParagraphStyle(
        "ExportRechts",
        parent=zellenstil,
        alignment=TA_RIGHT,
    )

    story = [
        Paragraph("Benutzerliste", titel),
        Paragraph(
            f"Lizenzmanagement - Export vom {date.today().strftime('%d.%m.%Y')} "
            f"- {len(benutzer or [])} Benutzer",
            untertitel,
        ),
    ]

    aktive_filter = []
    for label, schluessel in (
        ("Suche", "suche"),
        ("Abteilung", "abteilung"),
        ("Benutzer", "benutzerstatus"),
        ("Lizenz", "lizenz"),
        ("Status", "lizenzstatus"),
    ):
        wert = str(filterdaten.get(schluessel) or "").strip()
        if wert and wert not in {
            "Alle Abteilungen",
            "Alle Lizenzen",
            "Alle Benutzer",
        }:
            aktive_filter.append(f"{label}: {wert}")

    filtertext = (
        "Filter: " + " | ".join(aktive_filter)
        if aktive_filter
        else "Filter: keine Einschränkung"
    )
    story.append(Paragraph(_text(filtertext), filterstil))

    daten = [[
        Paragraph("Vorname", kopfstil),
        Paragraph("Nachname", kopfstil),
        Paragraph("Abteilung", kopfstil),
        Paragraph("Status", kopfstil),
        Paragraph("Aktive Lizenz(en)", kopfstil),
    ]]

    for eintrag in benutzer or []:
        vorname = str(eintrag.get("vorname") or "").strip()
        nachname = str(eintrag.get("nachname") or "").strip()
        if not vorname or not nachname:
            name_vorname, name_nachname = name_aufteilen(
                eintrag.get("name")
            )
            vorname = vorname or name_vorname
            nachname = nachname or name_nachname
        lizenzen = eintrag.get("lizenzen") or []
        lizenztext = ", ".join(
            str(lizenz).strip()
            for lizenz in lizenzen
            if str(lizenz).strip()
        ) or "Keine aktive Lizenz"

        daten.append([
            Paragraph(_text(vorname), zellenstil),
            Paragraph(_text(nachname), zellenstil),
            Paragraph(_text(eintrag.get("abteilung")), zellenstil),
            Paragraph(_text(eintrag.get("status")), zellenstil),
            Paragraph(_text(lizenztext), zellenstil),
        ])

    if len(daten) == 1:
        daten.append([
            Paragraph("Keine Benutzer entsprechen den Filtern.", zellenstil),
            "",
            "",
            "",
            "",
        ])

    tabelle = Table(
        daten,
        colWidths=[36 * mm, 44 * mm, 58 * mm, 30 * mm, 86 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    tabellenstil = [
        (
            "BACKGROUND",
            (0, 0),
            (-1, 0),
            colors.HexColor("#2f6728"),
        ),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [colors.white, colors.HexColor("#f5f8f5")],
        ),
        (
            "LINEBELOW",
            (0, 0),
            (-1, -1),
            0.35,
            colors.HexColor("#dbe4dc"),
        ),
        (
            "BOX",
            (0, 0),
            (-1, -1),
            0.6,
            colors.HexColor("#cbd8cd"),
        ),
    ]
    if len(daten) == 2:
        tabellenstil.append(("SPAN", (0, 1), (-1, 1)))
    tabelle.setStyle(TableStyle(tabellenstil))
    story.extend([tabelle, Spacer(1, 8)])

    def _fusszeile(canvas, dokument):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbe4dc"))
        canvas.setLineWidth(0.5)
        canvas.line(
            rand,
            12 * mm,
            A4[0] - rand,
            12 * mm,
        )
        canvas.setFont(schrift_normal, 8)
        canvas.setFillColor(colors.HexColor("#718074"))
        canvas.drawString(rand, 7 * mm, "Lizenzmanagement")
        canvas.drawRightString(
            A4[0] - rand,
            7 * mm,
            f"Seite {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=_fusszeile,
        onLaterPages=_fusszeile,
    )
    return puffer.getvalue()
