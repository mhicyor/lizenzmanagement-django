from copy import deepcopy


REST_VORLAGEN = {
    "eigene_rest_api": {
        "name": "Eigene REST-API",
        "beschreibung": (
            "Freie REST-Datenquelle mit eigener URL, "
            "Authentifizierung und Feldzuordnung."
        ),
        "typ": "rest_api",
        "auth_typ": "keine",
        "basis_url": "",
        "endpunkt": "",
        "zuweisungen_endpunkt": "",
        "token_url": "",
        "scope": "",
        "feld_mapping": {},
        "zuweisungen_feld_mapping": {},
        "hinweise": [
            "Geeignet für eigene oder interne APIs.",
            "Felder werden nach dem Verbindungstest automatisch erkannt.",
        ],
    },
    "adobe_user_management": {
        "name": "Adobe User Management API",
        "beschreibung": (
            "Vorlage für Adobe-Benutzer- und "
            "Lizenzzuweisungsdaten über eine REST-API."
        ),
        "typ": "rest_api",
        "auth_typ": "oauth2_client_credentials",
        "basis_url": "https://usermanagement.adobe.io",
        "endpunkt": (
            "/v2/usermanagement/users/{org_id}/0"
        ),
        "zuweisungen_endpunkt": "",
        "token_url": (
            "https://ims-na1.adobelogin.com/ims/token/v3"
        ),
        "scope": (
            "openid,AdobeID,user_management_sdk"
        ),
        "feld_mapping": {
            "externe_id": "email",
            "lizenzname": "groups",
            "status": "status",
        },
        "zuweisungen_feld_mapping": {
            "benutzer_externe_id": "email",
            "email": "email",
            "benutzername": "username",
            "status": "status",
        },
        "zusaetzliche_header": [
            {
                "name": "x-api-key",
                "wert": "{client_id}",
            }
        ],
        "hinweise": [
            "Adobe ist hier nur eine Vorlage für eine REST-Datenquelle.",
            "Client-ID und Client-Secret werden nicht in der Vorlage gespeichert.",
            "Die Org-ID muss später über Parameter oder Endpoint ersetzt werden.",
        ],
    },
}


def rest_vorlagen_laden():
    return deepcopy(REST_VORLAGEN)


def rest_vorlage_laden(schluessel):
    schluessel = str(
        schluessel or ""
    ).strip()

    if not schluessel:
        return None

    vorlage = REST_VORLAGEN.get(
        schluessel
    )

    if vorlage is None:
        return None

    return deepcopy(vorlage)


def rest_vorlage_auswahl_laden():
    auswahl = []

    for schluessel, vorlage in REST_VORLAGEN.items():
        auswahl.append(
            {
                "schluessel": schluessel,
                "name": vorlage.get(
                    "name",
                    schluessel,
                ),
                "beschreibung": vorlage.get(
                    "beschreibung",
                    "",
                ),
                "auth_typ": vorlage.get(
                    "auth_typ",
                    "",
                ),
            }
        )

    return auswahl
