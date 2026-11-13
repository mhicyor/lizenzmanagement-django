from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from ad_service import (
    ad_benutzer_mit_protokoll_synchronisieren,
    ad_verbindung_testen,
)
from sync_config_service import pruefe_sync_konfiguration


@login_required
def adobe_import(request):
    return redirect(
        "/synchronisation/"
        "?sync_status=info"
        "&sync_meldung=Adobe+wird+jetzt+als+REST-Datenquelle+verwaltet"
    )


@login_required
def ad_synchronisation(request):
    konfiguration = pruefe_sync_konfiguration("ad")
    verbindung_ergebnis = None
    sync_ergebnis = None

    if request.method == "POST":
        aktion = request.POST.get("aktion")

        if aktion == "verbindung_testen":
            erfolgreich, meldung = ad_verbindung_testen()

            verbindung_ergebnis = {
                "erfolgreich": erfolgreich,
                "meldung": meldung,
            }

        if aktion == "benutzer_synchronisieren":
            sync_ergebnis = (
                ad_benutzer_mit_protokoll_synchronisieren(
                    ausgeloest_durch="manuell",
                )
            )

    return render(
        request,
        "lizenzen/ad_synchronisation.html",
        {
            "konfiguration": konfiguration,
            "verbindung_ergebnis": verbindung_ergebnis,
            "sync_ergebnis": sync_ergebnis,
        }
    )
