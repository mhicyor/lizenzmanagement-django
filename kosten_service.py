def wert_zu_float(wert):
    try:
        return float(str(wert or 0).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def berechne_monatskosten(kosten, kostenmodell, menge):
    kosten = wert_zu_float(kosten)
    kostenmodell = kostenmodell or "fortlaufend"
    menge = menge or 0

    # ``fortlaufend`` ist der bisherige Wert für monatliche Kosten.
    if kostenmodell in {"fortlaufend", "monatlich"}:
        return kosten * menge

    if kostenmodell in {"jaehrlich", "jährlich"}:
        return (kosten * menge) / 12

    if kostenmodell == "einmalig":
        return 0

    return kosten * menge


def kostenmodell_hinweis(kostenmodell):
    kostenmodell = kostenmodell or "fortlaufend"

    if kostenmodell in {"fortlaufend", "monatlich"}:
        return "Monatliche Kosten werden anhand des gesamten Lizenzbestands berechnet."

    if kostenmodell in {"jaehrlich", "jährlich"}:
        return "Jährliche Kosten werden für die Monatsübersicht auf ein Zwölftel umgerechnet."

    if kostenmodell == "einmalig":
        return "Einmalige Kosten werden dokumentiert, erhöhen die laufenden Gesamtkosten aber nicht automatisch."

    return "Unbekanntes Kostenmodell. Es wird wie fortlaufend behandelt."
