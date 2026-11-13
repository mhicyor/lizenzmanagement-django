from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from geraete_service import (
    geraet_aktualisieren,
    geraet_hinzufuegen,
    geraet_loeschen,
    lade_geraet_details,
    lade_geraete_uebersicht,
)
from lizenz_logik_service import (
    ermittle_lizenz_ziel_typ,
    ist_datenquellen_lizenz,
)
from lizenz_service import (
    entferne_lizenzzuweisung_flexibel,
    lade_lizenz_details,
    lade_lizenz_ziele,
    weise_lizenz_an_ziel_zu,
)
from server_service import (
    lade_server_details,
    lade_server_uebersicht,
    server_aktualisieren,
    server_hinzufuegen,
    server_loeschen,
)

from .view_helpers import (
    _eindeutige_spaltenwerte,
    _eintraege_filtern,
    _formularfelder_aus_post,
    _ist_modal_anfrage,
    _modal_darstellung,
    _modal_nachricht_response,
)


@login_required
def geraete_liste(request):
    suchtext = request.GET.get(
        "suche",
        "",
    ).strip()
    suchwert = suchtext.lower()

    geraetetyp_filter = request.GET.get(
        "geraetetyp",
        "Alle Gerätetypen",
    ).strip()

    status_filter = request.GET.get(
        "status",
        "Alle Status",
    ).strip()

    alle_geraete = lade_geraete_uebersicht()
    herkunft_filter = request.GET.get("herkunft", "alle").strip()
    if herkunft_filter not in {"alle", "manuell", "datenquelle"}:
        herkunft_filter = "alle"
    sortierung = request.GET.get("sortierung", "name").strip()
    sortierungen = {
        "name": "Name A–Z",
        "erstellt_neu": "Hinzugefügt: neueste zuerst",
        "erstellt_alt": "Hinzugefügt: älteste zuerst",
    }
    if sortierung not in sortierungen:
        sortierung = "name"

    geraetetypen = _eindeutige_spaltenwerte(
        alle_geraete,
        4,
    )
    statuswerte = _eindeutige_spaltenwerte(
        alle_geraete,
        5,
    )
    statuswerte = sorted(set(statuswerte) | {"aktiv", "inaktiv", "archiviert"})

    geraete = []

    for geraet in _eintraege_filtern(
        alle_geraete,
        suchwert,
    ):

        geraetetyp = str(
            geraet[4] or ""
        ).strip()

        status = str(
            geraet[5] or ""
        ).strip()

        passt_geraetetyp = (
            geraetetyp_filter == "Alle Gerätetypen"
            or geraetetyp == geraetetyp_filter
        )

        passt_status = (
            status_filter == "Alle Status"
            or status == status_filter
        )
        herkunft = geraet[6] if len(geraet) > 6 else "manuell"
        passt_herkunft = herkunft_filter == "alle" or herkunft == herkunft_filter

        if (
            passt_geraetetyp
            and passt_status
            and passt_herkunft
        ):
            geraete.append(geraet)

    if sortierung != "name":
        datum_index = 7
        bekannte = [g for g in geraete if len(g) > datum_index and g[datum_index]]
        unbekannte = [g for g in geraete if len(g) <= datum_index or not g[datum_index]]
        bekannte.sort(
            key=lambda g: (g[datum_index], g[0]),
            reverse=sortierung.endswith("neu"),
        )
        geraete = bekannte + unbekannte

    geraete_seite = Paginator(geraete, 30).get_page(request.GET.get("seite"))
    filter_parameter = request.GET.copy()
    filter_parameter.pop("seite", None)

    return render(
        request,
        "lizenzen/geraete.html",
        {
            "geraete": list(geraete_seite),
            "geraete_seite": geraete_seite,
            "geraete_filter_query": filter_parameter.urlencode(),
            "suchtext": suchtext,
            "geraetetypen": geraetetypen,
            "geraetetyp_filter": geraetetyp_filter,
            "statuswerte": statuswerte,
            "status_filter": status_filter,
            "herkunft_filter": herkunft_filter,
            "sortierung": sortierung,
            "sortierungen": sortierungen,
            "geraete_statistik": {
                "gesamt": len(alle_geraete),
                "aktiv": sum(
                    1
                    for geraet in alle_geraete
                    if str(
                        geraet[5] or ""
                    ).strip().lower() == "aktiv"
                ),
                "geraetetypen": len(geraetetypen),
                "angezeigt": len(geraete),
            },
        },
    )


@login_required
def server_liste(request):
    server = lade_server_uebersicht()

    return render(
        request,
        "lizenzen/server.html",
        {
            "server": server,
        },
    )


@login_required
@xframe_options_sameorigin
def geraet_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    fehler = ""

    formular_daten = {
        "name": "",
        "inventarnummer": "",
        "seriennummer": "",
        "geraetetyp": "",
    }

    if request.method == "POST":
        formular_daten = _formularfelder_aus_post(
            request,
            formular_daten,
        )
        name = formular_daten["name"]
        inventarnummer = formular_daten["inventarnummer"]
        seriennummer = formular_daten["seriennummer"]
        geraetetyp = formular_daten["geraetetyp"]

        if not name:
            fehler = (
                "Bitte mindestens einen Gerätenamen eintragen."
            )
        else:
            geraet_hinzufuegen(
                name,
                inventarnummer,
                seriennummer,
                geraetetyp,
            )

            if ist_modal:
                return _modal_nachricht_response(
                    "geraet_gespeichert"
                )

            next_ziel = request.GET.get("next", "")

            if next_ziel == "zuweisen":
                return redirect(
                    "/lizenzen/zuweisen/?typ=geraet"
                )

            return redirect("geraete_liste")

    return render(
        request,
        "lizenzen/geraet_hinzufuegen.html",
        {
            "fehler": fehler,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
            "formular_daten": formular_daten,
        },
    )


@login_required
def server_hinzufuegen_view(request):
    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hostname = request.POST.get("hostname", "").strip()
        ip_adresse = request.POST.get("ip_adresse", "").strip()
        betriebssystem = request.POST.get("betriebssystem", "").strip()

        if name == "":
            fehler = "Bitte mindestens einen Servernamen eintragen."
        else:
            server_hinzufuegen(
                name,
                hostname,
                ip_adresse,
                betriebssystem,
            )

        next_ziel = request.GET.get("next", "")

        if next_ziel == "zuweisen":
            return redirect("/lizenzen/zuweisen/?typ=server")

        return redirect("server_liste")

    return render(
        request,
        "lizenzen/server_hinzufuegen.html",
        {
            "fehler": fehler,
        },
    )


@login_required
def server_lizenz_zuweisen(request, lizenz_id):
    lizenz, _, _ = lade_lizenz_details(lizenz_id)

    fehler = ""
    erfolg = ""

    if lizenz is None:
        return render(
            request,
            "lizenzen/server_lizenz_zuweisen.html",
            {
                "lizenz": None,
                "server_liste": [],
                "fehler": "Die ausgewählte Lizenz existiert nicht.",
                "erfolg": "",
            },
        )

    if lizenz[8] != "server":
        fehler = (
            "Diese Lizenz ist keine Serverlizenz und kann keinem Server "
            "zugewiesen werden."
        )

    zugewiesene_server = lade_lizenz_ziele(lizenz_id, "server")
    zugewiesene_server_ids = [server[0] for server in zugewiesene_server]

    alle_server = lade_server_uebersicht()

    server_liste = [
        server for server in alle_server
        if server[0] not in zugewiesene_server_ids
    ]

    if request.method == "POST" and lizenz[8] == "server":
        server_id = request.POST.get("server_id", "")

        if server_id == "":
            fehler = "Bitte einen Server auswählen."
        else:
            erfolgreich, meldung = weise_lizenz_an_ziel_zu(
                lizenz_id,
                "server",
                server_id,
            )

            if erfolgreich:
                return redirect("lizenz_detail", lizenz_id=lizenz_id)

            fehler = meldung

    return render(
        request,
        "lizenzen/server_lizenz_zuweisen.html",
        {
            "lizenz": lizenz,
            "server_liste": server_liste,
            "fehler": fehler,
            "erfolg": erfolg,
        },
    )


@login_required
@xframe_options_sameorigin
def geraet_lizenz_zuweisen(request, lizenz_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    lizenz, _, _ = lade_lizenz_details(
        lizenz_id
    )

    fehler = ""
    erfolg = ""

    if lizenz is None:
        return render(
            request,
            "lizenzen/geraet_lizenz_zuweisen.html",
            {
                "lizenz": None,
                "ziel_typ": "",
                "geraete_liste": [],
                "fehler": (
                    "Die ausgewählte Lizenz existiert nicht."
                ),
                "erfolg": "",
                "ist_modal": ist_modal,
                "template_basis": template_basis,
                "ist_datenquellen_lizenz": False,
            },
        )

    # Zieltyp zentral über den Service bestimmen.
    ziel_typ = ermittle_lizenz_ziel_typ(
        lizenz
    )

    # Verwaltungsart zentral über den Service prüfen.
    ist_datenquellen_lizenz_wert = (
        ist_datenquellen_lizenz(
            lizenz,
            datenquelle_index=18,
            api_sync_index=19,
        )
    )

    if ziel_typ != "geraet":
        fehler = (
            "Diese Lizenz ist keine Gerätelizenz und "
            "kann keinem Gerät zugewiesen werden."
        )

    elif ist_datenquellen_lizenz_wert:
        fehler = (
            "Diese Lizenz wird über eine Datenquelle "
            "verwaltet. Gerätezuweisungen werden durch "
            "die Synchronisation übernommen und können "
            "nicht manuell geändert werden."
        )

    # Bereits zugewiesene Geräte laden.
    zugewiesene_geraete = lade_lizenz_ziele(
        lizenz_id,
        "geraet",
    )

    zugewiesene_geraete_ids = {
        geraet[0]
        for geraet in zugewiesene_geraete
    }

    alle_geraete = lade_geraete_uebersicht()

    geraete_liste = [
        geraet
        for geraet in alle_geraete
        if geraet[0] not in zugewiesene_geraete_ids
    ]

    # Manuelle Gerätezuweisung speichern.
    if (
        request.method == "POST"
        and ziel_typ == "geraet"
        and not ist_datenquellen_lizenz_wert
    ):
        geraet_id = request.POST.get(
            "geraet_id",
            "",
        ).strip()

        if not geraet_id:
            fehler = "Bitte ein Gerät auswählen."

        else:
            erfolgreich, meldung = (
                weise_lizenz_an_ziel_zu(
                    lizenz_id,
                    "geraet",
                    geraet_id,
                )
            )

            if erfolgreich:
                detail_url = reverse(
                    "lizenz_detail",
                    args=[lizenz_id],
                )

                if ist_modal:
                    return redirect(
                        f"{detail_url}?modal=1"
                    )

                return redirect(
                    detail_url
                )

            fehler = meldung

    return render(
        request,
        "lizenzen/geraet_lizenz_zuweisen.html",
        {
            "lizenz": lizenz,
            "ziel_typ": ziel_typ,
            "geraete_liste": geraete_liste,
            "fehler": fehler,
            "erfolg": erfolg,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
            "ist_datenquellen_lizenz": (
                ist_datenquellen_lizenz_wert
            ),
        },
    )


@login_required
@xframe_options_sameorigin
def geraet_bearbeiten_view(request, geraet_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    geraet = lade_geraet_details(geraet_id)

    if geraet is None:
        return render(
            request,
            "lizenzen/geraet_bearbeiten.html",
            {
                "geraet": None,
                "fehler": "Das ausgewählte Gerät existiert nicht.",
                "ist_modal": ist_modal,
                "template_basis": template_basis,
            },
        )

    fehler = ""

    formular_daten = {
        "name": geraet[1] or "",
        "inventarnummer": geraet[2] or "",
        "seriennummer": geraet[3] or "",
        "geraetetyp": geraet[4] or "",
        "status": geraet[5] or "aktiv",
    }

    if request.method == "POST":
        formular_daten = _formularfelder_aus_post(
            request,
            {
                "name": "",
                "inventarnummer": "",
                "seriennummer": "",
                "geraetetyp": "",
                "status": "aktiv",
            },
        )
        name = formular_daten["name"]
        inventarnummer = formular_daten["inventarnummer"]
        seriennummer = formular_daten["seriennummer"]
        geraetetyp = formular_daten["geraetetyp"]
        status = formular_daten["status"]

        if not name:
            fehler = "Bitte einen Gerätenamen eingeben."
        else:
            geraet_aktualisieren(
                geraet_id,
                name,
                inventarnummer,
                seriennummer,
                geraetetyp,
                status,
            )

            if ist_modal:
                return _modal_nachricht_response(
                    "geraet_gespeichert"
                )

            return redirect("geraete_liste")

    return render(
        request,
        "lizenzen/geraet_bearbeiten.html",
        {
            "geraet": geraet,
            "fehler": fehler,
            "formular_daten": formular_daten,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        },
    )


@login_required
@require_POST
def geraet_loeschen_view(request, geraet_id):
    geraet_loeschen(geraet_id)

    return redirect("geraete_liste")


@login_required
def server_bearbeiten_view(request, server_id):
    server = lade_server_details(server_id)

    if server is None:
        return render(
            request,
            "lizenzen/server_bearbeiten.html",
            {
                "server": None,
                "fehler": "Der ausgewählte Server existiert nicht.",
            },
        )

    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hostname = request.POST.get("hostname", "").strip()
        ip_adresse = request.POST.get("ip_adresse", "").strip()
        betriebssystem = request.POST.get("betriebssystem", "").strip()
        status = request.POST.get("status", "aktiv").strip()

        if not name:
            fehler = "Bitte einen Servernamen eingeben."
        else:
            server_aktualisieren(
                server_id,
                name,
                hostname,
                ip_adresse,
                betriebssystem,
                status,
            )

            return redirect("server_liste")

    return render(
        request,
        "lizenzen/server_bearbeiten.html",
        {
            "server": server,
            "fehler": fehler,
        },
    )


@login_required
@require_POST
def server_loeschen_view(request, server_id):
    server_loeschen(server_id)

    return redirect("server_liste")


@login_required
@require_POST
def lizenz_zuweisung_entfernen_view(
    request,
    lizenz_id,
    ziel_typ,
    ziel_id,
):
    ist_modal = _ist_modal_anfrage(request)

    entferne_lizenzzuweisung_flexibel(
        lizenz_id,
        ziel_typ,
        ziel_id,
    )

    detail_url = reverse(
        "lizenz_detail",
        args=[lizenz_id],
    )

    if ist_modal:
        return redirect(
            f"{detail_url}?modal=1"
        )

    return redirect(detail_url)
