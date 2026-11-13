import json
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from requests.auth import HTTPBasicAuth

from api_feld_service import blattpfade_ermitteln

from rest_gruppen_analyse_service import (
    gruppe_klassifizieren,
)
from rest_anbieterprofil_service import (
    antwort_timeout_fuer_url,
    api_key_id_hinweis_fuer_url,
)


STANDARD_TIMEOUT = 20
MAX_VORSCHAU_DATENSAETZE = 3
MAX_API_SEITEN = 100
# Marker used by a direct user-license source.  It deliberately does not
# contain a provider name: the source name is supplied by the connection
# configuration and the marker is persisted as the source's generic rule.
ALLE_BENUTZER_MARKER = "__alle_benutzer__"

# Kept as a compatibility alias for existing integrations/tests.  New code
# must use ``ALLE_BENUTZER_MARKER`` so a provider name is never baked into the
# synchronization logic.
SOSAFE_ALLE_BENUTZER_MARKER = ALLE_BENUTZER_MARKER

# Rules created by older releases used a provider-specific marker.  Reading
# it remains supported so an upgrade does not silently drop assignments.
_LEGACY_DIREKTE_BENUTZER_MARKER = "__sosafe_alle_benutzer__"

BENUTZER_GRUPPEN_FELDER = (
    "groups",
    "gruppen",
    "usergroup",
    "usergroups",
    "user_group",
    "user_groups",
    "productprofiles",
    "product_profiles",
    "licenses",
    "lizenzen",
    "entitlements",
    "subscriptions",
    "plans",
    # Common organisational fields.  They are interpreted as department
    # data only when the response is recognised as a direct user source;
    # otherwise the normal group/product classification still applies.
    "department",
    "departmentname",
    "abteilung",
    "organization",
    "organisation",
    "orgunit",
    "division",
)

ERLAUBTE_AUTH_TYPEN = {
    "keine",
    "api_key",
    "api_key_token_exchange",
    "basic_auth",
    "bearer_token",
    "oauth2_client_credentials",
}


class RestApiFehler(Exception):
    """
    Verständlicher Fehler für den REST-API-Assistenten.
    """


def _text_bereinigen(wert):
    return str(wert or "").strip()


def _url_pruefen(url, feldname):
    url = _text_bereinigen(url)

    if not url:
        raise RestApiFehler(
            f"Bitte {feldname} eingeben."
        )

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise RestApiFehler(
            f"{feldname} muss mit "
            "https:// oder http:// beginnen."
        )

    if not parsed.hostname:
        raise RestApiFehler(
            f"{feldname} enthält keinen "
            "gültigen Hostnamen."
        )

    return url


def _api_url_erstellen(basis_url, endpunkt):
    basis_url = _url_pruefen(
        basis_url,
        "eine gültige Basis-URL",
    )

    endpunkt = _text_bereinigen(endpunkt)

    basis_mit_schraegstrich = (
        basis_url
        if basis_url.endswith("/")
        else basis_url + "/"
    )

    api_url = urljoin(
        basis_mit_schraegstrich,
        endpunkt.lstrip("/"),
    )

    return _url_pruefen(
        api_url,
        "eine gültige API-Adresse",
    )


def _api_timeout_bestimmen(geprueft):
    """Return request/response timeouts for the configured API.

    Some API gateways need a longer response window.  The value can be
    supplied by the connection configuration; the default stays conservative
    and provider agnostic.  ``sosafe_antwort_timeout`` is accepted only as a
    migration fallback for connections created by older versions.
    """
    try:
        timeout = int(geprueft.get("api_timeout", STANDARD_TIMEOUT))
    except (TypeError, ValueError):
        timeout = STANDARD_TIMEOUT

    try:
        antwort_timeout = int(
            geprueft.get(
                "api_response_timeout",
                timeout,
            )
        )
    except (TypeError, ValueError):
        antwort_timeout = timeout

    # A documented source-specific timeout is retained as a compatibility
    # fallback for existing connections. New integrations can set the
    # generic ``api_response_timeout`` value instead.
    if (
        not geprueft.get("api_response_timeout_configured")
    ):
        profil_timeout = antwort_timeout_fuer_url(
            geprueft.get("api_url", "")
        )

        if profil_timeout is not None:
            antwort_timeout = profil_timeout

    timeout = max(1, min(timeout, 300))
    antwort_timeout = max(timeout, min(antwort_timeout, 300))

    if antwort_timeout != timeout:
        return timeout, antwort_timeout

    return timeout


def _api_antwort_timeout_bestimmen(geprueft):
    timeout = _api_timeout_bestimmen(
        geprueft
    )

    if isinstance(timeout, tuple):
        return timeout[1]

    return timeout


def _anbietername_aus_api_url(api_url):
    """Create a readable fallback source name from an API host.

    A configured connection name always wins.  This fallback only makes
    direct user-license previews useful for callers that use the low-level
    preview helper without a full data-source configuration.
    """
    hostname = str(urlparse(str(api_url or "")).hostname or "").strip()
    teile = [teil for teil in hostname.split(".") if teil]

    while len(teile) > 1 and teile[0].lower() in {
        "api",
        "connect",
        "www",
    }:
        teile.pop(0)

    if not teile:
        return "Benutzerquelle"

    return teile[0].replace("-", " ").strip().title() or "Benutzerquelle"


def _gruppenwert_ist_skalar(wert):
    """Whether a group field contains one scalar value.

    A direct user-license endpoint typically exposes one department or
    account group per user.  APIs that expose a list of entitlements/groups
    remain in the generic ``benutzer_gruppen`` mode.
    """
    if isinstance(wert, (list, tuple, set, dict)):
        return False

    return bool(str(wert or "").strip())


def _gruppenwert_ist_direkt(wert):
    """Accept scalar values and one-element scalar containers.

    A few APIs serialize a single department as ``["Department"]`` even
    though the field is semantically singular.  Multiple values still mean
    real group/product data and therefore stay in ``benutzer_gruppen`` mode.
    """
    if _gruppenwert_ist_skalar(wert):
        return True

    if isinstance(wert, (list, tuple, set)) and len(wert) == 1:
        return _gruppenwert_ist_direkt(next(iter(wert)))

    if isinstance(wert, dict):
        return any(
            _gruppenwert_ist_skalar(wert.get(schluessel))
            for schluessel in (
                "name",
                "displayName",
                "title",
                "value",
            )
        )

    return False


def _direkte_gruppenwert_lesen(wert):
    """Return the normalized department/group label for direct sources."""
    if isinstance(wert, (list, tuple, set)):
        if len(wert) != 1:
            return ""
        wert = next(iter(wert))

    if isinstance(wert, dict):
        for schluessel in (
            "name",
            "displayName",
            "title",
            "value",
        ):
            if wert.get(schluessel):
                return str(wert[schluessel]).strip()
        return ""

    return str(wert or "").strip()


def _ist_direkte_benutzerlizenzquelle(
    datensaetze,
    gruppen_feld,
    api_url="",
):
    """Detect a user endpoint whose records share one direct licence.

    Detection is intentionally based on response shape and endpoint role,
    not on a provider/domain name.  The endpoint must look like a user
    collection and expose a scalar group/department field for its records.
    """
    if not gruppen_feld:
        return False

    pfad = str(urlparse(str(api_url or "")).path or "").rstrip("/").lower()
    ressourcenname = pfad.rsplit("/", 1)[-1] if pfad else ""
    if ressourcenname not in {
        "user",
        "users",
        "member",
        "members",
        "people",
        "accounts",
        "employee",
        "employees",
        "staff",
        "directory",
    }:
        normierter_name = ressourcenname.replace("-", "_")
        if not any(
            teil in normierter_name.split("_")
            for teil in (
                "user",
                "users",
                "member",
                "members",
                "people",
                "account",
                "accounts",
                "employee",
                "employees",
                "staff",
            )
        ):
            return False

    benutzerdatensaetze = [
        datensatz
        for datensatz in (datensaetze or [])
        if isinstance(datensatz, dict)
        and _gruppenwert_ist_direkt(datensatz.get(gruppen_feld))
    ]

    if not benutzerdatensaetze:
        return False

    # Avoid classifying a mixed response (some users with arrays, some with
    # scalar values) as a direct source.
    return all(
        _gruppenwert_ist_direkt(datensatz.get(gruppen_feld))
        for datensatz in (datensaetze or [])
        if isinstance(datensatz, dict)
    )


def _zusaetzliche_header_pruefen(header_daten):
    if not header_daten:
        return {}

    if isinstance(header_daten, str):
        try:
            header_daten = json.loads(
                header_daten
            )
        except json.JSONDecodeError as fehler:
            raise RestApiFehler(
                "Die zusätzlichen HTTP-Header "
                "sind ungültig."
            ) from fehler

    if not isinstance(header_daten, list):
        raise RestApiFehler(
            "Die zusätzlichen HTTP-Header "
            "müssen als Liste übergeben werden."
        )

    header = {}

    for eintrag in header_daten:
        if not isinstance(eintrag, dict):
            continue

        name = _text_bereinigen(
            eintrag.get("name")
        )

        wert = _text_bereinigen(
            eintrag.get("wert")
        )

        if not name and not wert:
            continue

        if not name or not wert:
            raise RestApiFehler(
                "Bei zusätzlichen HTTP-Headern "
                "müssen Name und Wert vollständig "
                "angegeben werden."
            )

        if any(
            zeichen in name
            for zeichen in ("\r", "\n")
        ):
            raise RestApiFehler(
                "Ein Header-Name enthält "
                "ungültige Zeichen."
            )

        if any(
            zeichen in wert
            for zeichen in ("\r", "\n")
        ):
            raise RestApiFehler(
                "Ein Header-Wert enthält "
                "ungültige Zeichen."
            )

        header[name] = wert

    return header


def rest_api_konfiguration_pruefen(
    konfiguration,
):
    name = _text_bereinigen(
        konfiguration.get("name")
    )

    if not name:
        raise RestApiFehler(
            "Bitte einen Namen für die "
            "Verbindung eingeben."
        )

    basis_url = _text_bereinigen(
        konfiguration.get("basis_url")
    )

    endpunkt = _text_bereinigen(
        konfiguration.get("endpunkt")
    )

    auth_typ = _text_bereinigen(
        konfiguration.get("auth_typ")
    ).lower() or "oauth2_client_credentials"

    if auth_typ not in ERLAUBTE_AUTH_TYPEN:
        raise RestApiFehler(
            "Die gewählte Anmeldeart "
            "wird nicht unterstützt."
        )

    api_url = _api_url_erstellen(
        basis_url,
        endpunkt,
    )

    geprueft = {
        "name": name,
        "basis_url": basis_url,
        "endpunkt": endpunkt,
        "api_url": api_url,
        "auth_typ": auth_typ,
        "api_key_header": _text_bereinigen(
            konfiguration.get(
                "api_key_header"
            )
        ),
        "api_key": _text_bereinigen(
            konfiguration.get("api_key")
        ),
        "api_key_id": _text_bereinigen(
            konfiguration.get("api_key_id")
        ),
        "basic_benutzername": (
            _text_bereinigen(
                konfiguration.get(
                    "basic_benutzername"
                )
            )
        ),
        "basic_passwort": str(
            konfiguration.get(
                "basic_passwort",
                "",
            )
        ),
        "bearer_token": _text_bereinigen(
            konfiguration.get(
                "bearer_token"
            )
        ),
        "token_url": _text_bereinigen(
            konfiguration.get("token_url")
        ),
        "client_id": _text_bereinigen(
            konfiguration.get("client_id")
        ),
        "client_secret": str(
            konfiguration.get(
                "client_secret",
                "",
            )
        ),
        "scope": _text_bereinigen(
            konfiguration.get("scope")
        ),
        "api_timeout": konfiguration.get(
            "api_timeout",
            STANDARD_TIMEOUT,
        ),
        "api_response_timeout": konfiguration.get(
            "api_response_timeout",
            konfiguration.get(
                "sosafe_antwort_timeout",
                STANDARD_TIMEOUT,
            ),
        ),
        "api_response_timeout_configured": (
            "api_response_timeout" in konfiguration
            or "sosafe_antwort_timeout" in konfiguration
        ),
        "zusaetzliche_header": (
            _zusaetzliche_header_pruefen(
                konfiguration.get(
                    "zusaetzliche_header"
                )
            )
        ),
    }

    if auth_typ in {
        "api_key",
        "api_key_token_exchange",
    }:
        if not geprueft["api_key_header"]:
            raise RestApiFehler(
                "Bitte den Header-Namen für "
                "den API-Key eingeben."
            )

        if not geprueft["api_key"]:
            raise RestApiFehler(
                "Bitte den API-Key eingeben."
            )

        if auth_typ == (
            "api_key_token_exchange"
        ):
            geprueft["token_url"] = (
                _url_pruefen(
                    geprueft["token_url"],
                    "eine gültige Anmelde-URL",
                )
            )

            api_key_id_hinweis = (
                api_key_id_hinweis_fuer_url(
                    basis_url
                )
            )

            if (
                api_key_id_hinweis
                and not geprueft["api_key_id"]
            ):
                raise RestApiFehler(
                    api_key_id_hinweis
                )

    elif auth_typ == "basic_auth":
        if not api_url.lower().startswith(
            "https://"
        ):
            raise RestApiFehler(
                "Benutzername und Passwort "
                "dürfen nur über HTTPS "
                "übertragen werden."
            )

        if not geprueft[
            "basic_benutzername"
        ]:
            raise RestApiFehler(
                "Bitte den Benutzernamen "
                "eingeben."
            )

        if not geprueft["basic_passwort"]:
            raise RestApiFehler(
                "Bitte das Passwort eingeben."
            )

    elif auth_typ == "bearer_token":
        if not geprueft["bearer_token"]:
            raise RestApiFehler(
                "Bitte das Bearer-Token "
                "eingeben."
            )

    elif auth_typ == (
        "oauth2_client_credentials"
    ):
        geprueft["token_url"] = (
            _url_pruefen(
                geprueft["token_url"],
                "eine gültige Token-URL",
            )
        )

        if not geprueft["client_id"]:
            raise RestApiFehler(
                "Bitte die Client-ID eingeben."
            )

        if not geprueft["client_secret"]:
            raise RestApiFehler(
                "Bitte das Client-Secret "
                "eingeben."
            )

    return geprueft


def rest_api_token_abrufen(
    konfiguration,
):
    token_daten = {
        "grant_type": "client_credentials",
        "client_id": (
            konfiguration["client_id"]
        ),
        "client_secret": (
            konfiguration["client_secret"]
        ),
    }

    if konfiguration["scope"]:
        token_daten["scope"] = (
            konfiguration["scope"]
        )

    try:
        antwort = requests.post(
            konfiguration["token_url"],
            data=token_daten,
            headers={
                "Accept": "application/json",
            },
            timeout=STANDARD_TIMEOUT,
            allow_redirects=False,
        )
    except requests.Timeout as fehler:
        raise RestApiFehler(
            "Die Anmeldung hat zu lange "
            "gedauert."
        ) from fehler
    except requests.ConnectionError as fehler:
        raise RestApiFehler(
            "Der Anmeldeserver konnte nicht "
            "erreicht werden."
        ) from fehler
    except requests.RequestException as fehler:
        raise RestApiFehler(
            "Die OAuth-Anmeldung konnte nicht "
            "ausgeführt werden."
        ) from fehler

    if antwort.status_code not in {
        200,
        201,
    }:
        raise RestApiFehler(
            "Die OAuth-Anmeldung wurde "
            "abgelehnt. "
            f"HTTP {antwort.status_code}."
        )

    try:
        token_antwort = antwort.json()
    except ValueError as fehler:
        raise RestApiFehler(
            "Der Anmeldeserver hat keine "
            "gültige JSON-Antwort geliefert."
        ) from fehler

    access_token = _text_bereinigen(
        token_antwort.get("access_token")
    )

    if not access_token:
        raise RestApiFehler(
            "Die OAuth-Antwort enthält "
            "kein Access Token."
        )

    return access_token


def _zugriffstoken_aus_antwort(
    token_antwort,
):
    """
    Erkennt die üblichen Feldnamen von Token-Antworten.

    Anbieter verwenden dafür leider keine einheitliche
    Bezeichnung. Es werden bewusst nur bekannte Token-Felder
    und typische Antwortcontainer berücksichtigt.
    """
    if isinstance(token_antwort, str):
        return _text_bereinigen(token_antwort)

    if not isinstance(token_antwort, dict):
        return ""

    token_felder = (
        "access_token",
        "accessToken",
        "token",
        "jwt",
        "jwt_token",
        "jwtToken",
        "id_token",
        "idToken",
    )

    for feld in token_felder:
        token = token_antwort.get(feld)

        if isinstance(token, str):
            token = _text_bereinigen(token)

            if token:
                return token

    for container in (
        "data",
        "result",
        "auth",
        "authentication",
    ):
        token = _zugriffstoken_aus_antwort(
            token_antwort.get(container)
        )

        if token:
            return token

    return ""


def rest_api_api_key_token_abrufen(
    konfiguration,
):
    """
    Tauscht einen API-Key gegen ein kurzlebiges Zugriffstoken.

    Dieses Verfahren wird unter anderem von SoSafe verwendet:
    POST an die Anmelde-URL mit dem API-Key im Header, danach
    GET auf den Datenendpunkt mit dem erhaltenen Bearer-Token.
    """
    header = {
        "Accept": "application/json",
        "User-Agent": (
            "DPZ-Lizenzmanagement/1.0"
        ),
        konfiguration["api_key_header"]: (
            konfiguration["api_key"]
        ),
    }

    anfrage_argumente = {}

    if konfiguration["api_key_id"]:
        anfrage_argumente["json"] = {
            "keyId": konfiguration[
                "api_key_id"
            ]
        }

    try:
        antwort = requests.post(
            konfiguration["token_url"],
            headers=header,
            timeout=STANDARD_TIMEOUT,
            allow_redirects=False,
            **anfrage_argumente,
        )
    except requests.Timeout as fehler:
        raise RestApiFehler(
            "Die automatische Anmeldung hat "
            "zu lange gedauert."
        ) from fehler
    except requests.ConnectionError as fehler:
        raise RestApiFehler(
            "Der Anmeldeserver konnte nicht "
            "erreicht werden."
        ) from fehler
    except requests.RequestException as fehler:
        raise RestApiFehler(
            "Die automatische Anmeldung konnte "
            "nicht ausgeführt werden."
        ) from fehler

    if antwort.status_code in {
        301,
        302,
        307,
        308,
    }:
        raise RestApiFehler(
            "Die Anmelde-URL hat weitergeleitet. "
            "Bitte die Anmelde-URL prüfen."
        )

    if antwort.status_code == 401:
        raise RestApiFehler(
            "Der API-Key wurde bei der Anmeldung "
            "abgelehnt. Bitte den API-Key prüfen."
        )

    if antwort.status_code == 403:
        raise RestApiFehler(
            "Der API-Key besitzt nicht die nötigen "
            "Berechtigungen."
        )

    if antwort.status_code == 404:
        raise RestApiFehler(
            "Die Anmelde-URL wurde nicht gefunden."
        )

    if antwort.status_code not in {
        200,
        201,
    }:
        raise RestApiFehler(
            "Die automatische Anmeldung wurde "
            "abgelehnt. "
            f"HTTP {antwort.status_code}."
        )

    try:
        token_antwort = antwort.json()
    except ValueError:
        token_antwort = _text_bereinigen(
            antwort.text
        )

    access_token = (
        _zugriffstoken_aus_antwort(
            token_antwort
        )
    )

    if not access_token:
        raise RestApiFehler(
            "Die Anmeldung war erfolgreich, aber "
            "die Antwort enthält kein Zugriffstoken."
        )

    return access_token


def _anfrage_vorbereiten(
    konfiguration,
):
    header = {
        "Accept": "application/json",
        "User-Agent": (
            "DPZ-Lizenzmanagement/1.0"
        ),
    }

    header.update(
        konfiguration[
            "zusaetzliche_header"
        ]
    )

    auth = None
    auth_typ = konfiguration["auth_typ"]

    if auth_typ == "api_key":
        header[
            konfiguration[
                "api_key_header"
            ]
        ] = konfiguration["api_key"]

    elif auth_typ == (
        "api_key_token_exchange"
    ):
        access_token = (
            rest_api_api_key_token_abrufen(
                konfiguration
            )
        )

        header["Authorization"] = (
            "Bearer " + access_token
        )

    elif auth_typ == "basic_auth":
        auth = HTTPBasicAuth(
            konfiguration[
                "basic_benutzername"
            ],
            konfiguration[
                "basic_passwort"
            ],
        )

    elif auth_typ == "bearer_token":
        header["Authorization"] = (
            "Bearer "
            + konfiguration[
                "bearer_token"
            ]
        )

    elif auth_typ == (
        "oauth2_client_credentials"
    ):
        access_token = (
            rest_api_token_abrufen(
                konfiguration
            )
        )

        header["Authorization"] = (
            "Bearer " + access_token
        )

    return header, auth


def _datenliste_erkennen(json_daten):
    if isinstance(json_daten, list):
        return json_daten, "wurzel"

    if isinstance(json_daten, dict):
        moegliche_felder = (
            "items",
            "data",
            "results",
            "products",
            "licenses",
            "users",
            "records",
            "value",
        )

        for feld in moegliche_felder:
            wert = json_daten.get(feld)

            if isinstance(wert, list):
                return wert, feld

        enthaltene_listen = [
            (feld, wert)
            for feld, wert in json_daten.items()
            if isinstance(wert, list)
        ]

        if len(enthaltene_listen) == 1:
            feld, wert = enthaltene_listen[0]
            return wert, feld

        return [json_daten], "objekt"

    return [], "unbekannt"


def _produktkandidaten_erkennen(
    datensaetze,
    gruppen_feld="groups",
):
    produktdefinitionen = (
        {
            "name": "Adobe Acrobat Pro",
            "muster": (
                "acrobat",
            ),
        },
        {
            "name": "Adobe Creative Cloud",
            "muster": (
                "creative cloud",
                "all apps",
                "photoshop",
                "illustrator",
                "indesign",
                "premiere",
                "after effects",
                "lightroom",
                "audition",
            ),
        },
    )

    produkte = {
        definition["name"]: {
            "name": definition["name"],
            "benutzer": set(),
            "externe_gruppen": set(),
        }
        for definition in produktdefinitionen
    }

    nicht_zugeordnete_gruppen = {}

    for datensatz_index, datensatz in enumerate(datensaetze):
        if not isinstance(datensatz, dict):
            continue

        gruppen = datensatz.get(gruppen_feld)

        if isinstance(gruppen, list):
            gruppen_liste = gruppen
        elif gruppen:
            gruppen_liste = [gruppen]
        else:
            gruppen_liste = []

        for gruppe in gruppen_liste:
            if isinstance(gruppe, dict):
                gruppenname = ""

                for name_feld in (
                    "name",
                    "displayName",
                    "productName",
                    "title",
                    "id",
                ):
                    if gruppe.get(name_feld):
                        gruppenname = str(
                            gruppe[name_feld]
                        ).strip()
                        break
            else:
                gruppenname = str(
                    gruppe or ""
                ).strip()

            if not gruppenname:
                continue

            text = gruppenname.lower()

            if gruppe_klassifizieren(gruppenname) == "technisch":
                continue

            bekannte_familie = False

            for definition in produktdefinitionen:
                if any(
                    muster in text
                    for muster in definition["muster"]
                ):
                    produktname = definition["name"]

                    produkte[produktname]["benutzer"].add(
                        datensatz_index
                    )

                    produkte[
                        produktname
                    ]["externe_gruppen"].add(
                        gruppenname
                    )

                    bekannte_familie = True
                    break

            if bekannte_familie:
                continue

            gruppendaten = nicht_zugeordnete_gruppen.setdefault(
                gruppenname,
                {
                    "benutzer": set(),
                    "klassifikation": gruppe_klassifizieren(
                        gruppenname
                    ),
                },
            )
            gruppendaten["benutzer"].add(datensatz_index)

    for gruppenname, gruppendaten in (
        nicht_zugeordnete_gruppen.items()
    ):
        if gruppendaten["klassifikation"] not in {
            "produktprofil",
            "mapping_kandidat",
        }:
            continue

        produkte[gruppenname] = {
            "name": gruppenname,
            "benutzer": gruppendaten["benutzer"],
            "externe_gruppen": {gruppenname},
        }

    hat_produktkandidaten = any(
        produkt["benutzer"]
        for produkt in produkte.values()
    )

    if not hat_produktkandidaten:
        fallback_gruppen = sorted(
            nicht_zugeordnete_gruppen.items(),
            key=lambda eintrag: (
                -len(eintrag[1]["benutzer"]),
                eintrag[0].lower(),
            ),
        )[:12]

        for gruppenname, gruppendaten in fallback_gruppen:
            produkte[gruppenname] = {
                "name": gruppenname,
                "benutzer": gruppendaten["benutzer"],
                "externe_gruppen": {gruppenname},
            }

    ergebnis = []

    for produkt in produkte.values():
        anzahl_benutzer = len(produkt["benutzer"])

        if anzahl_benutzer < 1:
            continue

        ergebnis.append(
            {
                "name": produkt["name"],
                "anzahl_benutzer": anzahl_benutzer,
                "externe_gruppen": sorted(
                    produkt["externe_gruppen"]
                ),
            }
        )

    return sorted(
        ergebnis,
        key=lambda produkt: (
            -produkt["anzahl_benutzer"],
            produkt["name"].lower(),
        ),
    )


def _gruppen_feld_erkennen(erkannte_felder):
    felder_nach_normalisiertem_namen = {
        str(feld).strip().lower(): feld
        for feld in erkannte_felder
    }

    for gruppen_feld in BENUTZER_GRUPPEN_FELDER:
        treffer = felder_nach_normalisiertem_namen.get(
            gruppen_feld.lower()
        )

        if treffer:
            return treffer

    return "groups"


def _organisationsfeld_erkennen(
    datensaetze,
    erkannte_felder,
):
    """Find a singular organisational field for user-directory responses.

    Directory APIs sometimes return both product groups and a department.
    The department is the stable attribute for the AD comparison and must
    therefore win over a multi-valued product/group field.
    """
    felder_nach_normalisiertem_namen = {
        str(feld).strip().lower(): feld
        for feld in erkannte_felder
    }

    for feldname in (
        "department",
        "departmentname",
        "abteilung",
        "organization",
        "organisation",
        "orgunit",
        "division",
    ):
        feld = felder_nach_normalisiertem_namen.get(
            feldname
        )

        if not feld:
            continue

        werte = [
            datensatz.get(feld)
            for datensatz in (datensaetze or [])
            if isinstance(datensatz, dict)
        ]

        if werte and all(
            _gruppenwert_ist_direkt(wert)
            for wert in werte
        ):
            return feld

    return ""


def _rest_datenart_erkennen(
    datensaetze,
    erkannte_felder,
):
    felder = {
        str(feld).strip().lower()
        for feld in erkannte_felder
    }

    hat_benutzerfeld = bool(
        felder.intersection(
            {
                "email",
                "mail",
                "username",
                "user",
                "userprincipalname",
                "benutzername",
            }
        )
    )

    hat_gruppenfeld = bool(
        felder.intersection(
            BENUTZER_GRUPPEN_FELDER
        )
    )

    if hat_benutzerfeld and hat_gruppenfeld:
        return "benutzer_gruppen"

    return "lizenzbestand"


def rest_api_json_vorschau_erstellen(
    json_daten,
    api_url="",
    datenquelle_name="",
):
    datensaetze, listen_pfad = (
        _datenliste_erkennen(
            json_daten
        )
    )

    erkannte_felder = set()

    for datensatz in datensaetze[
        :MAX_VORSCHAU_DATENSAETZE
    ]:
        if isinstance(datensatz, dict):
            # Bestehende Verbindungen und die fachliche Gruppen-Erkennung
            # verwenden weiterhin die Container-Namen. Zusaetzlich werden
            # die neuen verschachtelten Blattpfade angeboten.
            erkannte_felder.update(datensatz.keys())
            erkannte_felder.update(
                blattpfade_ermitteln(datensatz)
            )

    beispiele = datensaetze[
        :MAX_VORSCHAU_DATENSAETZE
    ]

    rest_datenart = _rest_datenart_erkennen(
        datensaetze,
        erkannte_felder,
    )

    gruppen_feld = _gruppen_feld_erkennen(
        erkannte_felder
    )

    organisationsfeld = _organisationsfeld_erkennen(
        datensaetze,
        erkannte_felder,
    )

    ist_direkte_benutzerlizenzquelle = (
        _ist_direkte_benutzerlizenzquelle(
            datensaetze,
            organisationsfeld or gruppen_feld,
            api_url,
        )
    )

    if ist_direkte_benutzerlizenzquelle:
        rest_datenart = "benutzer_lizenz"
        gruppen_feld = organisationsfeld or gruppen_feld

    if ist_direkte_benutzerlizenzquelle:
        quellenname = str(datenquelle_name or "").strip()

        if not quellenname:
            quellenname = _anbietername_aus_api_url(api_url)

        produktkandidaten = [
            {
                "name": quellenname,
                "anzahl_benutzer": len(
                    datensaetze
                ),
                "externe_gruppen": [
                    ALLE_BENUTZER_MARKER
                ],
                "zuweisungsmodus": (
                    "alle_benutzer"
                ),
            }
        ]
    else:
        produktkandidaten = (
            _produktkandidaten_erkennen(
                datensaetze,
                gruppen_feld,
            )
        )

    abteilungen = {}

    if ist_direkte_benutzerlizenzquelle:
        for datensatz in datensaetze:
            if not isinstance(
                datensatz,
                dict,
            ):
                continue

            abteilung = _direkte_gruppenwert_lesen(
                datensatz.get(gruppen_feld, "")
            )

            if abteilung:
                abteilungen[abteilung] = (
                    abteilungen.get(
                        abteilung,
                        0,
                    )
                    + 1
                )

    return {
        "rest_datenart": rest_datenart,
        "quellbezeichnung": (
            str(datenquelle_name or "").strip()
            or _anbietername_aus_api_url(api_url)
        ),
        "anzahl_datensaetze": (
            len(datensaetze)
        ),
        "listen_pfad": listen_pfad,
        "gruppen_feld": gruppen_feld,
        "gruppen_semantik": (
            "abteilung"
            if ist_direkte_benutzerlizenzquelle
            else "produktprofil"
        ),
        "anzahl_abteilungen": len(
            abteilungen
        ),
        "erkannte_felder": sorted(
            erkannte_felder
        ),
        "beispiele": beispiele,
        "produktkandidaten": produktkandidaten,
    }

def _rest_api_json_anfragen(
    geprueft,
):
    header, auth = (
        _anfrage_vorbereiten(
            geprueft
        )
    )

    timeout = _api_timeout_bestimmen(
        geprueft
    )

    antwort_timeout = (
        _api_antwort_timeout_bestimmen(
            geprueft
        )
    )

    try:
        antwort = requests.get(
            geprueft["api_url"],
            headers=header,
            auth=auth,
            timeout=timeout,
            allow_redirects=False,
        )

    except requests.Timeout as fehler:
        raise RestApiFehler(
            "Die API hat nicht innerhalb "
            f"von {antwort_timeout} Sekunden "
            "geantwortet."
        ) from fehler

    except requests.ConnectionError as fehler:
        raise RestApiFehler(
            "Die Verbindung zur API konnte "
            "nicht hergestellt werden."
        ) from fehler

    except requests.RequestException as fehler:
        raise RestApiFehler(
            "Die API-Anfrage konnte nicht "
            "ausgeführt werden."
        ) from fehler

    if antwort.status_code in {
        301,
        302,
        307,
        308,
    }:
        raise RestApiFehler(
            "Die API hat auf eine andere "
            "Adresse weitergeleitet. Bitte "
            "Basis-URL und Endpunkt prüfen."
        )

    if antwort.status_code == 400:
        raise RestApiFehler(
            "Die API hat die Anfrage als "
            "ungültig abgelehnt."
        )

    if antwort.status_code == 401:
        raise RestApiFehler(
            "Die Anmeldung wurde abgelehnt. "
            "Bitte die Zugangsdaten prüfen."
        )

    if antwort.status_code == 403:
        raise RestApiFehler(
            "Der Zugriff auf diesen Endpunkt "
            "ist nicht erlaubt."
        )

    if antwort.status_code == 404:
        raise RestApiFehler(
            "Der angegebene API-Endpunkt "
            "wurde nicht gefunden."
        )

    if antwort.status_code == 429:
        raise RestApiFehler(
            "Das API-Limit wurde erreicht. "
            "Bitte später erneut versuchen."
        )

    if not 200 <= antwort.status_code < 300:
        raise RestApiFehler(
            "Die API antwortete mit "
            f"HTTP {antwort.status_code}."
        )

    try:
        json_daten = antwort.json()

    except ValueError as fehler:
        raise RestApiFehler(
            "Die Verbindung war erfolgreich, "
            "aber die Antwort enthält kein "
            "gültiges JSON."
        ) from fehler

    return antwort, json_daten


def _naechste_api_seite_url(json_daten, aktuelle_url):
    """Erkennt verbreitete Link-, Cursor- und Seitenschemata generisch."""
    if not isinstance(json_daten, dict):
        return None

    links = json_daten.get("links")
    seiten = json_daten.get("pages")
    naechster_wert = json_daten.get("next")

    if isinstance(links, dict):
        naechster_wert = links.get("next") or naechster_wert

    if isinstance(naechster_wert, dict):
        naechster_wert = (
            naechster_wert.get("href")
            or naechster_wert.get("url")
        )

    if isinstance(naechster_wert, str) and naechster_wert.strip():
        return urljoin(aktuelle_url, naechster_wert.strip())

    next_key = json_daten.get("nextKey")
    if isinstance(seiten, dict):
        next_key = seiten.get("nextKey") or next_key

    if next_key not in (None, ""):
        parsed = urlparse(aktuelle_url)
        parameter = dict(parse_qsl(parsed.query, keep_blank_values=True))
        parameter["pageFromKey"] = str(next_key)
        return urlunparse(parsed._replace(query=urlencode(parameter)))

    if isinstance(seiten, dict):
        aktuell = seiten.get("current") or seiten.get("page")
        gesamt = seiten.get("total") or seiten.get("totalPages")
        try:
            aktuell = int(aktuell)
            gesamt = int(gesamt)
        except (TypeError, ValueError):
            return None

        if aktuell < gesamt:
            parsed = urlparse(aktuelle_url)
            parameter = dict(parse_qsl(parsed.query, keep_blank_values=True))
            parameter["page"] = str(aktuell + 1)
            return urlunparse(parsed._replace(query=urlencode(parameter)))

    return None


def rest_api_daten_abrufen(
    konfiguration,
):
    """
    Ruft die vollständigen JSON-Daten einer REST-API ab.

    Im Gegensatz zum Verbindungstest werden hier nicht nur
    Vorschaudaten, sondern alle erkannten Datensätze
    zurückgegeben.
    """
    geprueft = (
        rest_api_konfiguration_pruefen(
            konfiguration
        )
    )

    antwort, json_daten = (
        _rest_api_json_anfragen(
            geprueft
        )
    )

    datensaetze, listen_pfad = (
        _datenliste_erkennen(
            json_daten
        )
    )

    alle_datensaetze = list(datensaetze)
    besuchte_urls = {geprueft["api_url"]}
    aktuelle_url = geprueft["api_url"]
    seitenzahl = 1

    while seitenzahl < MAX_API_SEITEN:
        naechste_url = _naechste_api_seite_url(json_daten, aktuelle_url)
        if not naechste_url or naechste_url in besuchte_urls:
            break

        # Die Folgeseite darf nicht unbemerkt auf einen anderen Host zeigen.
        if urlparse(naechste_url).hostname != urlparse(geprueft["api_url"]).hostname:
            raise RestApiFehler(
                "Die API verweist für die nächste Seite auf einen anderen Host."
            )

        folgekonfiguration = dict(geprueft)
        folgekonfiguration["api_url"] = naechste_url
        _, json_daten = _rest_api_json_anfragen(folgekonfiguration)
        folgedaten, folgepfad = _datenliste_erkennen(json_daten)

        if folgepfad != listen_pfad and listen_pfad not in {"wurzel", "objekt"}:
            raise RestApiFehler(
                "Die API hat auf einer Folgeseite eine andere Datenstruktur geliefert."
            )

        alle_datensaetze.extend(folgedaten)
        besuchte_urls.add(naechste_url)
        aktuelle_url = naechste_url
        seitenzahl += 1

    return {
        "http_status": antwort.status_code,
        "api_url": geprueft["api_url"],
        "listen_pfad": listen_pfad,
        "datensaetze": alle_datensaetze,
        "json_daten": json_daten,
        "seitenzahl": seitenzahl,
    }

def rest_api_endpunkt_testen(
    konfiguration,
    endpunkt,
):
    alternative_konfiguration = dict(
        konfiguration
    )

    alternative_konfiguration["endpunkt"] = (
        endpunkt
    )

    return rest_api_verbindung_testen(
        alternative_konfiguration
    )


def rest_api_verbindung_testen(
    konfiguration,
):
    geprueft = (
        rest_api_konfiguration_pruefen(
            konfiguration
        )
    )

    antwort, json_daten = (
        _rest_api_json_anfragen(
            geprueft
        )
    )

    vorschau = (
        rest_api_json_vorschau_erstellen(
            json_daten,
            api_url=geprueft["api_url"],
            datenquelle_name=geprueft.get("name", ""),
        )
    )

    return {
        "erfolgreich": True,
        "meldung": (
            "Verbindung erfolgreich. "
            f"{vorschau['anzahl_datensaetze']} "
            "Datensätze wurden erkannt."
        ),
        "http_status": (
            antwort.status_code
        ),
        "api_url": geprueft["api_url"],
        "vorschau": vorschau,
    }


def rest_api_rohdaten_laden(konfiguration):
    """
    Lädt REST-Daten ohne fachliche Verarbeitung.
    Wird für REST-Datenarten verwendet, die nicht direkt
    als Lizenzbestand verarbeitet werden.
    """
    return rest_api_daten_abrufen(konfiguration)
