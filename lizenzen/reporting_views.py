from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from auswertung_service import (
    lade_ablaufende_lizenzen,
    lade_deaktivierte_benutzer_mit_lizenzen,
)
from lizenz_service import (
    lade_kostenuebersicht,
    lade_lizenzuebersicht,
)

from .view_helpers import _modal_darstellung


@login_required
def auswertungen(request):
    lizenzbestand = lade_lizenzuebersicht()

    kostenbericht_daten = lade_kostenuebersicht()
    kostenbericht = kostenbericht_daten.get("daten", [])
    gesamtsumme = kostenbericht_daten.get("gesamtsumme", 0)

    ablaufende_lizenzen = lade_ablaufende_lizenzen(30)
    deaktivierte_benutzer = lade_deaktivierte_benutzer_mit_lizenzen()

    return render(
        request,
        "lizenzen/auswertungen.html",
        {
            "lizenzbestand": lizenzbestand,
            "kostenbericht": kostenbericht,
            "gesamtsumme": gesamtsumme,
            "ablaufende_lizenzen": ablaufende_lizenzen,
            "deaktivierte_benutzer": deaktivierte_benutzer,
        },
    )


@login_required
def lizenzbestand(request):
    daten = lade_lizenzuebersicht()

    return render(
        request,
        "lizenzen/lizenzbestand.html",
        {
            "daten": daten,
        },
    )


@login_required
def kostenbericht(request):
    kostenbericht_daten = lade_kostenuebersicht()
    daten = kostenbericht_daten.get("daten", [])
    gesamtsumme = kostenbericht_daten.get("gesamtsumme", 0)

    return render(
        request,
        "lizenzen/kostenbericht.html",
        {
            "daten": daten,
            "gesamtsumme": gesamtsumme,
        },
    )


@login_required
@xframe_options_sameorigin
def ablaufende_lizenzen(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )
    daten = lade_ablaufende_lizenzen(30)

    return render(
        request,
        "lizenzen/ablaufende_lizenzen.html",
        {
            "daten": daten,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )
