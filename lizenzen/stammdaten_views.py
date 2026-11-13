"""Views fuer Anbieter- und Lizenzkategorie-Stammdaten."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from anbieter_service import (
    anbieter_aktualisieren,
    anbieter_deaktivieren,
    anbieter_hinzufuegen,
    anbieter_loeschen,
    anbieter_reaktivieren,
    anzahl_lizenzen_mit_anbieter,
    lade_anbieter,
    lade_anbieter_details,
)
from lizenz_kategorie_service import (
    anzahl_lizenzen_mit_kategorie,
    lade_lizenz_kategorie,
    lade_lizenz_kategorien,
    lizenz_kategorie_aktualisieren,
    lizenz_kategorie_deaktivieren,
    lizenz_kategorie_hinzufuegen,
    lizenz_kategorie_loeschen,
    lizenz_kategorie_reaktivieren,
)

from .view_helpers import (
    _ist_modal_anfrage,
    _modal_darstellung,
    _modal_nachricht_response,
    modal_parent_reload_response,
)


@login_required
@xframe_options_sameorigin
def anbieter_liste_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    anbieter = lade_anbieter(nur_aktive=False)
    anbieter_liste = []

    for eintrag in anbieter:
        anbieter_id = eintrag[0]
        name = eintrag[1]
        beschreibung = eintrag[2]
        webseite = eintrag[3]
        aktiv = bool(eintrag[4])
        erstellt_am = eintrag[5] if len(eintrag) > 5 else ""
        aktualisiert_am = eintrag[6] if len(eintrag) > 6 else ""

        anbieter_liste.append({
            "id": anbieter_id,
            "name": name,
            "beschreibung": beschreibung,
            "webseite": webseite,
            "aktiv": aktiv,
            "erstellt_am": erstellt_am,
            "aktualisiert_am": aktualisiert_am,
            "anzahl_lizenzen": anzahl_lizenzen_mit_anbieter(name),
        })

    aktive_anbieter = [
        eintrag for eintrag in anbieter_liste
        if eintrag["aktiv"]
    ]

    inaktive_anbieter = [
        eintrag for eintrag in anbieter_liste
        if not eintrag["aktiv"]
    ]

    return render(
        request,
        "lizenzen/anbieter.html",
        {
            "anbieter": anbieter_liste,
            "aktive_anbieter": aktive_anbieter,
            "inaktive_anbieter": inaktive_anbieter,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@xframe_options_sameorigin
def anbieter_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        webseite = request.POST.get("webseite", "").strip()

        erfolgreich, meldung, neue_id = anbieter_hinzufuegen(
            name,
            beschreibung,
            webseite
        )

        if erfolgreich:
            if ist_modal:
                return _modal_nachricht_response({
                    "type": "anbieter_gespeichert",
                    "anbieter": {"id": neue_id, "name": name},
                })

            next_ziel = request.GET.get("next", "")

            if next_ziel == "lizenz_hinzufuegen":
                return redirect("lizenz_hinzufuegen")

            return redirect("anbieter_liste")

        fehler = meldung

    return render(
        request,
        "lizenzen/anbieter_hinzufuegen.html",
        {
            "fehler": fehler,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@xframe_options_sameorigin
def anbieter_bearbeiten_view(request, anbieter_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    anbieter = lade_anbieter_details(anbieter_id)

    if anbieter is None:
        return render(
            request,
            "lizenzen/anbieter_bearbeiten.html",
            {
                "anbieter": None,
                "fehler": "Der ausgewählte Anbieter existiert nicht.",
                "ist_modal": ist_modal,
                "template_basis": template_basis,
            }
        )

    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        webseite = request.POST.get("webseite", "").strip()
        aktiv = request.POST.get("aktiv", "1").strip()

        erfolgreich, meldung = anbieter_aktualisieren(
            anbieter_id,
            name,
            beschreibung,
            webseite,
            aktiv
        )

        if erfolgreich:
            if ist_modal:
                return modal_parent_reload_response("anbieter_gespeichert")

            return redirect("anbieter_liste")

        fehler = meldung

        anbieter = (
            anbieter_id,
            name,
            beschreibung,
            webseite,
            int(aktiv) if aktiv in ["0", "1"] else 1,
            anbieter[5],
            anbieter[6],
        )

    return render(
        request,
        "lizenzen/anbieter_bearbeiten.html",
        {
            "anbieter": anbieter,
            "fehler": fehler,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@xframe_options_sameorigin
def lizenzkategorien_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    kategorien_roh = lade_lizenz_kategorien(
        nur_aktive=False,
        inklusive_archiviert=True
    )

    kategorien = []

    for kategorie in kategorien_roh:
        kategorie_id = kategorie[0]

        kategorien.append({
            "id": kategorie[0],
            "name": kategorie[1],
            "beschreibung": kategorie[2],
            "lizenzlogik": kategorie[3],
            "typische_zuordnung": kategorie[4],
            "interne_lizenzklasse": kategorie[5],
            "aktiv": bool(kategorie[6]),
            "slug": kategorie[7],
            "standard_zuweisungsart": kategorie[8],
            "archiviert": bool(kategorie[9]),
            "archiviert_am": kategorie[10],
            "archivierungsgrund": kategorie[11],
            "sortierung": kategorie[12],
            "erstellt_am": kategorie[13],
            "aktualisiert_am": kategorie[14],
            "anzahl_lizenzen": anzahl_lizenzen_mit_kategorie(kategorie_id),
        })

    aktive_kategorien = [
        kategorie for kategorie in kategorien
        if kategorie["aktiv"] and not kategorie["archiviert"]
    ]

    archivierte_kategorien = [
        kategorie for kategorie in kategorien
        if kategorie["archiviert"]
    ]

    return render(
        request,
        "lizenzen/lizenzkategorien.html",
        {
            "kategorien": kategorien,
            "aktive_kategorien": aktive_kategorien,
            "archivierte_kategorien": archivierte_kategorien,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@xframe_options_sameorigin
def lizenzkategorie_hinzufuegen_view(request):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        lizenzlogik = request.POST.get("lizenzlogik", "").strip()
        typische_zuordnung = request.POST.get("typische_zuordnung", "").strip()
        interne_lizenzklasse = request.POST.get(
            "interne_lizenzklasse",
            "benutzer",
        ).strip()
        standard_zuweisungsart = request.POST.get(
            "standard_zuweisungsart",
            interne_lizenzklasse,
        ).strip()
        sortierung = request.POST.get("sortierung", "100").strip()

        erfolgreich, meldung, neue_id = lizenz_kategorie_hinzufuegen(
            name,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            standard_zuweisungsart,
            sortierung
        )

        if erfolgreich:
            if ist_modal:
                return modal_parent_reload_response("kategorie_gespeichert")

            return redirect("lizenzkategorien")

        fehler = meldung

    return render(
        request,
        "lizenzen/lizenzkategorie_hinzufuegen.html",
        {
            "fehler": fehler,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@xframe_options_sameorigin
def lizenzkategorie_bearbeiten_view(request, kategorie_id):
    ist_modal, template_basis = _modal_darstellung(
        request
    )

    kategorie_roh = lade_lizenz_kategorie(kategorie_id)

    if kategorie_roh is None:
        return render(
            request,
            "lizenzen/lizenzkategorie_bearbeiten.html",
            {
                "kategorie": None,
                "fehler": "Die ausgewählte Kategorie existiert nicht.",
                "anzahl_lizenzen": 0,
                "ist_modal": ist_modal,
                "template_basis": template_basis,
            }
        )

    kategorie = {
        "id": kategorie_roh[0],
        "name": kategorie_roh[1],
        "beschreibung": kategorie_roh[2],
        "lizenzlogik": kategorie_roh[3],
        "typische_zuordnung": kategorie_roh[4],
        "interne_lizenzklasse": kategorie_roh[5],
        "aktiv": bool(kategorie_roh[6]),
        "slug": kategorie_roh[7],
        "standard_zuweisungsart": kategorie_roh[8],
        "archiviert": bool(kategorie_roh[9]),
        "archiviert_am": kategorie_roh[10],
        "archivierungsgrund": kategorie_roh[11],
        "sortierung": kategorie_roh[12],
        "erstellt_am": kategorie_roh[13],
        "aktualisiert_am": kategorie_roh[14],
    }

    anzahl_lizenzen = anzahl_lizenzen_mit_kategorie(kategorie_id)
    fehler = ""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        beschreibung = request.POST.get("beschreibung", "").strip()
        lizenzlogik = request.POST.get("lizenzlogik", "").strip()
        typische_zuordnung = request.POST.get("typische_zuordnung", "").strip()
        interne_lizenzklasse = request.POST.get(
            "interne_lizenzklasse",
            "benutzer",
        ).strip()
        standard_zuweisungsart = request.POST.get(
            "standard_zuweisungsart",
            interne_lizenzklasse,
        ).strip()
        aktiv = request.POST.get("aktiv", "1").strip()
        sortierung = request.POST.get("sortierung", "100").strip()

        erfolgreich, meldung = lizenz_kategorie_aktualisieren(
            kategorie_id,
            name,
            beschreibung,
            lizenzlogik,
            typische_zuordnung,
            interne_lizenzklasse,
            standard_zuweisungsart,
            aktiv,
            sortierung
        )

        if erfolgreich:
            if ist_modal:
                return modal_parent_reload_response("kategorie_gespeichert")

            return redirect("lizenzkategorien")

        fehler = meldung

        kategorie["name"] = name
        kategorie["beschreibung"] = beschreibung
        kategorie["lizenzlogik"] = lizenzlogik
        kategorie["typische_zuordnung"] = typische_zuordnung
        kategorie["interne_lizenzklasse"] = interne_lizenzklasse
        kategorie["standard_zuweisungsart"] = standard_zuweisungsart
        kategorie["aktiv"] = aktiv == "1"
        kategorie["sortierung"] = sortierung

    return render(
        request,
        "lizenzen/lizenzkategorie_bearbeiten.html",
        {
            "kategorie": kategorie,
            "fehler": fehler,
            "anzahl_lizenzen": anzahl_lizenzen,
            "ist_modal": ist_modal,
            "template_basis": template_basis,
        }
    )


@login_required
@require_POST
def anbieter_deaktivieren_view(request, anbieter_id):
    ist_modal = _ist_modal_anfrage(request)

    anbieter_deaktivieren(anbieter_id)

    if ist_modal:
        return redirect("/anbieter/?modal=1")

    return redirect("anbieter_liste")


@login_required
@require_POST
def anbieter_reaktivieren_view(request, anbieter_id):
    ist_modal = _ist_modal_anfrage(request)

    anbieter_reaktivieren(anbieter_id)

    if ist_modal:
        return redirect("/anbieter/?modal=1")

    return redirect("anbieter_liste")


@login_required
@require_POST
def anbieter_loeschen_view(request, anbieter_id):
    ist_modal = _ist_modal_anfrage(request)

    anbieter_loeschen(anbieter_id)

    if ist_modal:
        return redirect("/anbieter/?modal=1")

    return redirect("anbieter_liste")


@login_required
@require_POST
def lizenzkategorie_deaktivieren_view(request, kategorie_id):
    ist_modal = _ist_modal_anfrage(request)

    archivierungsgrund = request.POST.get("archivierungsgrund", "").strip()

    lizenz_kategorie_deaktivieren(
        kategorie_id,
        archivierungsgrund
    )

    if ist_modal:
        return modal_parent_reload_response("kategorie_gespeichert")

    return redirect("lizenzkategorien")


@login_required
@require_POST
def lizenzkategorie_reaktivieren_view(request, kategorie_id):
    ist_modal = _ist_modal_anfrage(request)

    lizenz_kategorie_reaktivieren(kategorie_id)

    if ist_modal:
        return modal_parent_reload_response("kategorie_gespeichert")

    return redirect("lizenzkategorien")


@login_required
@require_POST
def lizenzkategorie_loeschen_view(request, kategorie_id):
    ist_modal = _ist_modal_anfrage(request)

    lizenz_kategorie_loeschen(kategorie_id)

    if ist_modal:
        return modal_parent_reload_response("kategorie_gespeichert")

    return redirect("lizenzkategorien")
