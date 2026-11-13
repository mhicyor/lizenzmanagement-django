import csv
from io import StringIO

from benutzer_export_utils import name_aufteilen


def _csv_zelle(wert, fallback="-"):
    """Bereitet externe Werte sicher für Tabellenprogramme auf."""
    text = str(wert or "").strip() or fallback

    if text != "-" and text.startswith(("=", "+", "-", "@")):
        return f"'{text}"

    return text


def benutzerliste_csv_erstellen(benutzer):
    """Erzeugt eine Excel-taugliche CSV der gefilterten Benutzerliste."""
    ausgabe = StringIO(newline="")
    writer = csv.writer(
        ausgabe,
        delimiter=";",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    writer.writerow([
        "Vorname",
        "Nachname",
        "Benutzername",
        "E-Mail",
        "Abteilung",
        "Status",
        "Aktive Lizenz(en)",
    ])

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

        writer.writerow([
            _csv_zelle(vorname),
            _csv_zelle(nachname),
            _csv_zelle(eintrag.get("benutzername"), fallback=""),
            _csv_zelle(eintrag.get("email"), fallback=""),
            _csv_zelle(eintrag.get("abteilung"), fallback=""),
            _csv_zelle(eintrag.get("status")),
            _csv_zelle(lizenztext),
        ])

    return ausgabe.getvalue().encode("utf-8-sig")
