"""Einheitliche Gruende fuer lokal deaktivierte Benutzerkonten."""


AD_KONTO_DEAKTIVIERT = "ad_konto_deaktiviert"
NICHT_IM_AD_GEFUNDEN = "nicht_im_ad_gefunden"
NICHT_IN_QUELLE_GEFUNDEN = "nicht_in_quelle_gefunden"
IN_QUELLE_DEAKTIVIERT = "in_quelle_deaktiviert"
MANUELL_DEAKTIVIERT = "manuell_deaktiviert"
TECHNISCHES_KONTO = "technisches_konto"


_ANZEIGETEXTE = {
    AD_KONTO_DEAKTIVIERT: "Im AD deaktiviert",
    NICHT_IM_AD_GEFUNDEN: "Im AD nicht mehr gefunden",
    NICHT_IN_QUELLE_GEFUNDEN: (
        "In der Datenquelle nicht mehr gefunden"
    ),
    IN_QUELLE_DEAKTIVIERT: "In der Datenquelle deaktiviert",
    MANUELL_DEAKTIVIERT: "Manuell deaktiviert",
    TECHNISCHES_KONTO: "Technisches Konto",
}


def deaktivierungsgrund_anzeige(deaktivierungsgrund):
    """Liefert einen kurzen, nicht technischen Text fuer die Oberflaeche."""
    schluessel = str(deaktivierungsgrund or "").strip().lower()

    return _ANZEIGETEXTE.get(
        schluessel,
        "Grund noch nicht ermittelt",
    )
