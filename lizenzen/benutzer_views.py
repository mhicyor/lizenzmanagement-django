from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from auswertung_service import lade_deaktivierte_benutzer_mit_lizenzen
from benutzer_service import (
    benutzer_hinzufuegen,
    filtere_reale_benutzerkonten,
    lade_aktive_benutzer_ids_fuer_lizenz,
    lade_aktive_benutzer_ids_mit_lizenz,
    lade_benutzer_details,
    lade_benutzer_exportdaten,
    lade_benutzer_uebersicht,
)
from csv_export_service import benutzerliste_csv_erstellen
from lizenz_service import (
    entferne_lizenzzuweisung,
    lade_lizenzen_uebersicht,
)
from pdf_export_service import benutzerliste_pdf_erstellen

from .view_helpers import (
    _deaktivierte_benutzer_gruppieren,
    _eindeutige_spaltenwerte,
    _eintraege_filtern,
    _formularfelder_aus_post,
    _ist_modal_anfrage,
    _modal_darstellung,
    _modal_nachricht_response,
)


def _ist_personenbezogene_lizenz(lizenz):
    """Nur solche Lizenzen in Benutzerfiltern anbieten."""
    zuweisungsart = (
        str(lizenz[9] or "").strip().lower()
        if len(lizenz) > 9
        else ""
    )
    lizenzklasse = (
        str(lizenz[8] or "").strip().lower()
        if len(lizenz) > 8
        else ""
    )

    zielart = zuweisungsart or lizenzklasse or "benutzer"
    return zielart == "benutzer"


def _benutzer_filterdaten(request):
    suchtext = request.GET.get("suche", "").strip()
    suchwert = suchtext.lower()
    lizenzstatus_filter = request.GET.get(
        "lizenzstatus",
        "alle",
    ).strip().lower()
    benutzerstatus_filter = request.GET.get(
        "benutzerstatus",
        "aktiv",
    ).strip().lower()

    if lizenzstatus_filter not in {
        "alle",
        "mit",
        "ohne",
    }:
        lizenzstatus_filter = "alle"

    if benutzerstatus_filter not in {
        "aktiv",
        "deaktiviert",
        "alle",
    }:
        benutzerstatus_filter = "aktiv"

    alle_benutzer = filtere_reale_benutzerkonten(
        lade_benutzer_uebersicht(status_filter="alle")
    )
    abteilungen = [
        "Alle Abteilungen",
        *_eindeutige_spaltenwerte(
            alle_benutzer,
            4,
        ),
    ]
    gueltige_abteilungen = set(abteilungen[1:])
    ausgewaehlte_abteilungen = list(dict.fromkeys(
        wert
        for rohwert in request.GET.getlist("abteilung")
        if (wert := rohwert.strip()) in gueltige_abteilungen
    ))

    filter_lizenzen = [
        {
            "id": int(lizenz[0]),
            "name": str(lizenz[1] or "Unbenannte Lizenz"),
            "anbieter": str(lizenz[2] or ""),
        }
        for lizenz in lade_lizenzen_uebersicht()
        if str(lizenz[19] or "aktiv").lower()
        == "aktiv"
        and _ist_personenbezogene_lizenz(lizenz)
    ]

    gueltige_lizenz_ids = {
        lizenz["id"]
        for lizenz in filter_lizenzen
    }

    ausgewaehlte_lizenz_ids = []
    for rohwert in request.GET.getlist("lizenz"):
        try:
            lizenz_id = int(rohwert)
        except (TypeError, ValueError):
            continue
        if (
            lizenz_id in gueltige_lizenz_ids
            and lizenz_id not in ausgewaehlte_lizenz_ids
        ):
            ausgewaehlte_lizenz_ids.append(lizenz_id)

    if (
        not ausgewaehlte_lizenz_ids
        and any(
            str(wert).strip()
            for wert in request.GET.getlist("lizenz")
        )
    ):
        lizenzstatus_filter = "alle"

    if ausgewaehlte_lizenz_ids:
        if "lizenzstatus" not in request.GET:
            lizenzstatus_filter = "mit"
        elif lizenzstatus_filter == "alle":
            ausgewaehlte_lizenz_ids = []

    benutzer = _eintraege_filtern(
        alle_benutzer,
        suchwert,
    )

    if benutzerstatus_filter in {
        "aktiv",
        "deaktiviert",
    }:
        benutzer = [
            eintrag
            for eintrag in benutzer
            if str(eintrag[5] or "").strip().lower()
            == benutzerstatus_filter
        ]

    if ausgewaehlte_abteilungen:
        abteilungsauswahl = set(ausgewaehlte_abteilungen)
        benutzer = [
            eintrag
            for eintrag in benutzer
            if str(eintrag[4] or "").strip()
            in abteilungsauswahl
        ]

    if lizenzstatus_filter in {
        "mit",
        "ohne",
    }:
        if ausgewaehlte_lizenz_ids:
            zuweisungen = [
                lade_aktive_benutzer_ids_fuer_lizenz(lizenz_id)
                for lizenz_id in ausgewaehlte_lizenz_ids
            ]
            benutzer_mit_lizenz = set.union(*zuweisungen)
        else:
            benutzer_mit_lizenz = lade_aktive_benutzer_ids_mit_lizenz(
                status_filter=benutzerstatus_filter
            )

        benutzer = [
            eintrag
            for eintrag in benutzer
            if (
                int(eintrag[0])
                in benutzer_mit_lizenz
            )
            == (lizenzstatus_filter == "mit")
        ]

    benutzer_filter_query = urlencode(
        {
            "suche": suchtext,
            "abteilung": ausgewaehlte_abteilungen,
            "lizenz": ausgewaehlte_lizenz_ids,
            "lizenzstatus": lizenzstatus_filter,
            "benutzerstatus": benutzerstatus_filter,
        },
        doseq=True,
    )

    return {
        "alle_benutzer": alle_benutzer,
        "benutzer": benutzer,
        "suchtext": suchtext,
        "abteilungen": abteilungen,
        "abteilung_filter": (
            ausgewaehlte_abteilungen[0]
            if ausgewaehlte_abteilungen
            else "Alle Abteilungen"
        ),
        "ausgewaehlte_abteilungen": ausgewaehlte_abteilungen,
        "filter_lizenzen": filter_lizenzen,
        "lizenz_filter": (
            ausgewaehlte_lizenz_ids[0]
            if ausgewaehlte_lizenz_ids
            else 0
        ),
        "ausgewaehlte_lizenz_ids": ausgewaehlte_lizenz_ids,
        "lizenzstatus_filter": lizenzstatus_filter,
        "benutzerstatus_filter": benutzerstatus_filter,
        "benutzer_filter_query": benutzer_filter_query,
    }


@login_required
def benutzer_liste(request):
    filterdaten = _benutzer_filterdaten(request)
    benutzer_seite = Paginator(
        filterdaten["benutzer"],
        30,
    ).get_page(
        request.GET.get("seite")
    )

    return render(
        request,
        "lizenzen/benutzer.html",
        {
            "benutzer": benutzer_seite,
            "suchtext": filterdaten["suchtext"],
            "abteilungen": filterdaten["abteilungen"],
            "abteilung_filter": filterdaten["abteilung_filter"],
            "ausgewaehlte_abteilungen": filterdaten["ausgewaehlte_abteilungen"],
            "filter_lizenzen": filterdaten["filter_lizenzen"],
            "lizenz_filter": filterdaten["lizenz_filter"],
            "ausgewaehlte_lizenz_ids": filterdaten["ausgewaehlte_lizenz_ids"],
            "lizenzstatus_filter": filterdaten["lizenzstatus_filter"],
            "benutzerstatus_filter": filterdaten["benutzerstatus_filter"],
            "benutzer_filter_query": filterdaten["benutzer_filter_query"],
            "benutzer_statistik": {
                "aktiv": sum(
                    1
                    for eintrag in filterdaten["alle_benutzer"]
                    if str(eintrag[5] or "").strip().lower()
                    == "aktiv"
                ),
                "deaktiviert": sum(
                    1
                    for eintrag in filterdaten["alle_benutzer"]
                    if str(eintrag[5] or "").strip().lower()
                    == "deaktiviert"
                ),
                "abteilungen": max(
                    0,
                    len(filterdaten["abteilungen"]) - 1,
                ),
                "mit_email": sum(
                    1
                    for eintrag in filterdaten["alle_benutzer"]
                    if str(eintrag[3] or "").strip()
                ),
                "angezeigt": len(filterdaten["benutzer"]),
            },
        },
    )


@login_required
def benutzer_export_pdf(request):
    """Exportiert die vollständige, aktuell gefilterte Benutzerliste als PDF."""
    filterdaten = _benutzer_filterdaten(request)
    benutzer = lade_benutzer_exportdaten(
        [eintrag[0] for eintrag in filterdaten["benutzer"]]
    )

    pdf = benutzerliste_pdf_erstellen(
        benutzer,
        {
            "suche": filterdaten["suchtext"],
            "abteilung": (
                ", ".join(filterdaten["ausgewaehlte_abteilungen"])
                or "Alle Abteilungen"
            ),
            "lizenz": (
                ", ".join(
                    eintrag["name"]
                    for eintrag in filterdaten["filter_lizenzen"]
                    if eintrag["id"] in filterdaten["ausgewaehlte_lizenz_ids"]
                )
                or "Alle Lizenzen"
            ),
            "lizenzstatus": {
                "mit": (
                    "Mindestens eine ausgewählte Lizenz vorhanden"
                    if len(filterdaten["ausgewaehlte_lizenz_ids"]) > 1
                    else "Lizenz vorhanden"
                ),
                "ohne": (
                    "Keine der ausgewählten Lizenzen vorhanden"
                    if filterdaten["ausgewaehlte_lizenz_ids"]
                    else "Keine Lizenz vorhanden"
                ),
            }.get(
                filterdaten["lizenzstatus_filter"],
                "Alle Benutzer",
            ),
            "benutzerstatus": {
                "aktiv": "Aktive Benutzer",
                "deaktiviert": "Deaktivierte Benutzer",
                "alle": "Alle Benutzer",
            }.get(
                filterdaten["benutzerstatus_filter"],
                "Aktive Benutzer",
            ),
        },
    )

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        'attachment; filename="benutzerliste.pdf"'
    )
    return response


@login_required
def benutzer_export_csv(request):
    """Exportiert die vollständige, aktuell gefilterte Benutzerliste als CSV."""
    filterdaten = _benutzer_filterdaten(request)
    benutzer = lade_benutzer_exportdaten(
        [eintrag[0] for eintrag in filterdaten["benutzer"]]
    )
    csv_datei = benutzerliste_csv_erstellen(benutzer)

    response = HttpResponse(
        csv_datei,
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        'attachment; filename="benutzerliste.csv"'
    )
    return response


def _deaktivierte_benutzer_filterdaten(request):
    daten = lade_deaktivierte_benutzer_mit_lizenzen()
    alle_benutzer = _deaktivierte_benutzer_gruppieren(
        daten
    )

    suchtext = request.GET.get("suche", "").strip()
    suchwert = suchtext.lower()

    try:
        lizenz_filter = int(
            request.GET.get("lizenz", 0) or 0
        )
    except (TypeError, ValueError):
        lizenz_filter = 0

    lizenzen_nach_id = {
        int(lizenz["id"]): {
            "id": int(lizenz["id"]),
            "name": lizenz["name"],
        }
        for eintrag in alle_benutzer
        for lizenz in eintrag["lizenzen"]
        if lizenz.get("id") is not None
    }
    filter_lizenzen = sorted(
        lizenzen_nach_id.values(),
        key=lambda lizenz: lizenz["name"].casefold(),
    )

    if lizenz_filter not in lizenzen_nach_id:
        lizenz_filter = 0

    benutzer = alle_benutzer

    if suchwert:
        benutzer = [
            eintrag
            for eintrag in benutzer
            if suchwert
            in " ".join(
                [
                    eintrag["name"],
                    eintrag["email"],
                    eintrag["deaktivierungsgrund_anzeige"],
                    *[
                        lizenz["name"]
                        for lizenz in eintrag["lizenzen"]
                    ],
                ]
            ).lower()
        ]

    if lizenz_filter:
        benutzer = [
            eintrag
            for eintrag in benutzer
            if any(
                lizenz["id"] == lizenz_filter
                for lizenz in eintrag["lizenzen"]
            )
        ]

    return {
        "daten": daten,
        "alle_benutzer": alle_benutzer,
        "benutzer": benutzer,
        "suchtext": suchtext,
        "filter_lizenzen": filter_lizenzen,
        "lizenz_filter": lizenz_filter,
        "filter_aktiv": bool(
            suchtext
            or lizenz_filter
        ),
    }


def _deaktivierte_benutzer_exportdaten(benutzer):
    exportdaten = []

    for eintrag in benutzer:
        exportdaten.append(
            {
                "name": eintrag["name"],
                "email": eintrag["email"],
                "abteilung": eintrag["abteilung"],
                "status": eintrag[
                    "deaktivierungsgrund_anzeige"
                ],
                "lizenzen": [
                    lizenz["name"]
                    for lizenz in eintrag["lizenzen"]
                ],
            }
        )

    return exportdaten


@login_required
def deaktivierte_benutzer_export_pdf(request):
    """Exportiert deaktivierte Benutzer mit aktiven Zuweisungen als PDF."""
    filterdaten = _deaktivierte_benutzer_filterdaten(request)
    pdf = benutzerliste_pdf_erstellen(
        _deaktivierte_benutzer_exportdaten(filterdaten["benutzer"]),
        {
            "suche": filterdaten["suchtext"],
            "lizenz": next(
                (
                    lizenz["name"]
                    for lizenz in filterdaten["filter_lizenzen"]
                    if lizenz["id"] == filterdaten["lizenz_filter"]
                ),
                "",
            ),
            "lizenzstatus": "Deaktivierte Benutzer",
        },
    )

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        'attachment; filename="deaktivierte-benutzer-lizenzen.pdf"'
    )
    return response


@login_required
def deaktivierte_benutzer_export_csv(request):
    """Exportiert deaktivierte Benutzer mit aktiven Zuweisungen als CSV."""
    filterdaten = _deaktivierte_benutzer_filterdaten(request)
    csv_datei = benutzerliste_csv_erstellen(
        _deaktivierte_benutzer_exportdaten(filterdaten["benutzer"])
    )

    response = HttpResponse(
        csv_datei,
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        'attachment; filename="deaktivierte-benutzer-lizenzen.csv"'
    )
    return response


@login_required
@xframe_options_sameorigin
def benutzer_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    fehler = ""

    formular_daten = {
        "name": "",
        "benutzername": "",
        "email": "",
        "abteilung": "",
    }

    if request.method == "POST":
        formular_daten = _formularfelder_aus_post(
            request,
            formular_daten,
        )
        name = formular_daten["name"]
        benutzername = formular_daten["benutzername"]
        email = formular_daten["email"]
        abteilung = formular_daten["abteilung"]

        if name == "" or benutzername == "" or email == "":
            fehler = "Bitte Name, Benutzername und E-Mail ausfüllen."
        else:
            benutzer_hinzufuegen(
                name,
                benutzername,
                email,
                abteilung,
            )

            if ist_modal:
                return _modal_nachricht_response(
                    "benutzer_gespeichert"
                )

            return redirect("benutzer_liste")

    return render(
        request,
        "lizenzen/benutzer_hinzufuegen.html",
        {
            "fehler": fehler,
            "formular_daten": formular_daten,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
@xframe_options_sameorigin
def deaktivierte_benutzer(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )
    filterdaten = _deaktivierte_benutzer_filterdaten(request)
    daten = filterdaten["daten"]
    alle_benutzer = filterdaten["alle_benutzer"]
    benutzer = filterdaten["benutzer"]
    suchtext = filterdaten["suchtext"]
    lizenz_filter = filterdaten["lizenz_filter"]

    benutzer_seite = Paginator(
        benutzer,
        20,
    ).get_page(
        request.GET.get("seite")
    )

    anzahl_lizenzen = sum(
        eintrag["anzahl_lizenzen"]
        for eintrag in alle_benutzer
    )
    filter_parameter = {
        "suche": suchtext,
        "lizenz": lizenz_filter or "",
    }

    if ist_modal:
        filter_parameter["modal"] = "1"

    return render(
        request,
        "lizenzen/deaktivierte_benutzer.html",
        {
            "daten": daten,
            "benutzer": benutzer_seite,
            "suchtext": suchtext,
            "filter_lizenzen": filterdaten["filter_lizenzen"],
            "lizenz_filter": lizenz_filter,
            "filter_aktiv": filterdaten["filter_aktiv"],
            "ist_modal": ist_modal,
            "template_basis": template_basis,
            "filter_query": urlencode(
                filter_parameter
            ),
            "statistik": {
                "benutzer": len(alle_benutzer),
                "lizenzen": anzahl_lizenzen,
                "angezeigt": len(benutzer),
            },
        },
    )


@login_required
@xframe_options_sameorigin
def benutzer_detail(request, benutzer_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    benutzer, aktive_lizenzen, entfernte_lizenzen = (
        lade_benutzer_details(benutzer_id)
    )

    return render(
        request,
        "lizenzen/benutzer_detail.html",
        {
            "benutzer": benutzer,
            "lizenzen": aktive_lizenzen,
            "entfernte_lizenzen": entfernte_lizenzen,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
@require_POST
def lizenzzuweisung_entfernen(request, benutzer_id, lizenz_id):
    ist_modal = _ist_modal_anfrage(request)

    entferne_lizenzzuweisung(benutzer_id, lizenz_id)

    if ist_modal:
        detail_url = reverse(
            "benutzer_detail",
            args=[benutzer_id],
        )

        return redirect(
            f"{detail_url}?modal=1"
        )

    return redirect("benutzer_detail", benutzer_id=benutzer_id)
