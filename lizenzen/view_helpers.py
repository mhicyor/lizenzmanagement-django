"""Gemeinsame Hilfsfunktionen fuer Django-Views.

Diese Funktionen enthalten keine fachliche View-Logik. Sie kapseln nur
kleine wiederkehrende UI- und Filter-Aufgaben, damit ``views.py`` lesbarer
bleibt.
"""

import json

from django.http import HttpResponse


def _ist_modal_anfrage(request):
    return (
        request.GET.get("modal") == "1"
        or request.POST.get("modal") == "1"
    )


def _modal_darstellung(request):
    ist_modal = _ist_modal_anfrage(request)
    template_basis = (
        "lizenzen/modal_base.html"
        if ist_modal
        else "lizenzen/base.html"
    )
    return ist_modal, template_basis


def _modal_nachricht_response(nachricht):
    # Strukturierte Ergebnisse erlauben eine Aktualisierung ohne Formular-Reload.
    # Auch Anbieternamen mit HTML dürfen den Script-Block nicht beenden.
    nachricht_json = json.dumps(nachricht).replace("<", "\\u003c")

    return HttpResponse(
        f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Änderung gespeichert</title>
        </head>
        <body>
            <script>
                window.parent.postMessage(
                    {nachricht_json},
                    window.location.origin
                );
            </script>
        </body>
        </html>
        """
    )


def modal_parent_reload_response(message):
    message_json = json.dumps(str(message))

    return HttpResponse(f"""
        <script>
            try {{
                if (window.parent && window.parent !== window) {{
                    window.parent.postMessage(
                        {message_json},
                        window.location.origin
                    );

                    setTimeout(function () {{
                        window.parent.location.reload();
                    }}, 120);
                }} else {{
                    window.location.reload();
                }}
            }} catch (error) {{
                window.location.href = "/kategorien/";
            }}
        </script>
    """)


def _eintraege_filtern(eintraege, suchwert):
    eintraege = eintraege or []

    if not suchwert:
        return list(eintraege)

    return [
        eintrag
        for eintrag in eintraege
        if any(
            suchwert in str(wert or "").lower()
            for wert in eintrag
        )
    ]


def _eindeutige_spaltenwerte(eintraege, index):
    return sorted({
        str(eintrag[index] or "").strip()
        for eintrag in eintraege
        if len(eintrag) > index
        and str(eintrag[index] or "").strip()
    })


def _deaktivierte_benutzer_gruppieren(daten):
    benutzer_nach_id = {}

    for eintrag in daten:
        benutzer_id = eintrag.get("benutzer_id")
        schluessel = benutzer_id or (
            eintrag.get("benutzer"),
            eintrag.get("email"),
            eintrag.get("benutzername"),
        )

        benutzer = benutzer_nach_id.setdefault(
            schluessel,
            {
                "id": benutzer_id,
                "name": eintrag.get("benutzer") or "Unbekannt",
                "email": eintrag.get("email") or "",
                "abteilung": eintrag.get("abteilung") or "",
                "deaktivierungsgrund": (
                    eintrag.get("deaktivierungsgrund") or ""
                ),
                "deaktivierungsgrund_anzeige": (
                    eintrag.get("deaktivierungsgrund_anzeige")
                    or "Grund noch nicht ermittelt"
                ),
                "lizenzen": [],
                "_lizenz_schluessel": set(),
            },
        )

        lizenz_schluessel = (
            eintrag.get("lizenz_id"),
            eintrag.get("lizenz"),
        )

        if lizenz_schluessel in benutzer["_lizenz_schluessel"]:
            continue

        benutzer["_lizenz_schluessel"].add(
            lizenz_schluessel
        )
        benutzer["lizenzen"].append(
            {
                "id": eintrag.get("lizenz_id"),
                "name": eintrag.get("lizenz") or "Unbekannte Lizenz",
                "kosten": eintrag.get("kosten") or "",
            }
        )

    benutzer_liste = []

    for benutzer in benutzer_nach_id.values():
        benutzer.pop("_lizenz_schluessel", None)
        benutzer["anzahl_lizenzen"] = len(
            benutzer["lizenzen"]
        )
        benutzer_liste.append(benutzer)

    return benutzer_liste


def _formularfelder_aus_post(request, standardwerte):
    return {
        feldname: request.POST.get(
            feldname,
            standardwert,
        ).strip()
        for feldname, standardwert in standardwerte.items()
    }
