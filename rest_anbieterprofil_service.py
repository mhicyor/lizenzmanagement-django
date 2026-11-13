"""Kleine Kompatibilitaetsprofile fuer bekannte REST-Anbieter.

Die eigentliche REST-Anbindung bleibt generisch. Ein Profil beschreibt nur
Anbieterbesonderheiten, die sich nicht allein aus den frei konfigurierbaren
Feldern ableiten lassen, zum Beispiel dokumentierte Pfad-Aliase oder ein
laengeres Antwortzeitfenster.
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class RestAnbieterprofil:
    schluessel: str
    hostnamen: frozenset[str]
    assistent_basis_urls: frozenset[str]
    token_auth_typ: str
    standard_endpunkt: str
    endpunkt_aliase: frozenset[str]
    standard_token_url: str
    token_url_aliase: frozenset[str]
    standard_api_key_header: str = ""
    api_key_id_erforderlich: bool = False
    api_key_id_hinweis: str = ""
    antwort_timeout: int | None = None


_SOSAFE_PROFIL = RestAnbieterprofil(
    schluessel="sosafe",
    hostnamen=frozenset({"connect.sosafe.de"}),
    assistent_basis_urls=frozenset(
        {"https://connect.sosafe.de"}
    ),
    token_auth_typ="api_key_token_exchange",
    standard_endpunkt="/v1/users",
    endpunkt_aliase=frozenset(
        {
            "",
            "users",
            "v1/users",
        }
    ),
    standard_token_url=(
        "https://connect.sosafe.de/v1/auth/login"
    ),
    token_url_aliase=frozenset(
        {
            "",
            "https://connect.sosafe.de/auth/login",
            "https://connect.sosafe.de/v1/auth/login",
        }
    ),
    standard_api_key_header="X-Api-Key",
    api_key_id_erforderlich=True,
    api_key_id_hinweis=(
        "Bitte zusätzlich die SoSafe API-Key-ID (keyId) "
        "eingeben. Sie beginnt üblicherweise mit SSKI."
    ),
    antwort_timeout=60,
)

_ANBIETERPROFILE = (
    _SOSAFE_PROFIL,
)


def oeffentliche_assistent_profile():
    """Liefert ausschließlich nicht geheime Werte für das Frontend."""
    return [
        {
            "schluessel": profil.schluessel,
            "hostnamen": sorted(profil.hostnamen),
            "token_auth_typ": profil.token_auth_typ,
            "standard_endpunkt": profil.standard_endpunkt,
            "endpunkt_aliase": sorted(
                profil.endpunkt_aliase
            ),
            "standard_token_url": profil.standard_token_url,
            "token_url_aliase": sorted(
                profil.token_url_aliase
            ),
            "standard_api_key_header": (
                profil.standard_api_key_header
            ),
            "api_key_id_erforderlich": (
                profil.api_key_id_erforderlich
            ),
        }
        for profil in _ANBIETERPROFILE
    ]


def _text_normalisieren(wert):
    return str(wert or "").strip().rstrip("/").lower()


def _hostname_ermitteln(url):
    try:
        return str(urlparse(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def rest_anbieterprofil_fuer_url(url):
    """Liefert das Profil anhand des Hostnamens oder ``None``."""
    hostname = _hostname_ermitteln(url)

    for profil in _ANBIETERPROFILE:
        if hostname in profil.hostnamen:
            return profil

    return None


def assistent_anbieterprofil_fuer_basis_url(basis_url):
    """Löst nur exakt unterstützte Assistent-Basisadressen auf.

    Dadurch werden keine Defaults auf Unterpfade oder abweichende Protokolle
    angewendet. Frei konfigurierte REST-Verbindungen bleiben unverändert.
    """
    normalisiert = _text_normalisieren(basis_url)

    for profil in _ANBIETERPROFILE:
        if normalisiert in profil.assistent_basis_urls:
            return profil

    return None


def assistent_standardwerte_anwenden(
    basis_url,
    auth_typ,
    endpunkt,
    token_url,
):
    """Wendet nur bekannte, dokumentierte Pfad-Aliase an."""
    profil = assistent_anbieterprofil_fuer_basis_url(
        basis_url
    )

    if (
        profil is None
        or str(auth_typ or "").strip().lower()
        != profil.token_auth_typ
    ):
        return profil, endpunkt, token_url

    endpunkt_normalisiert = (
        str(endpunkt or "")
        .strip()
        .strip("/")
        .lower()
    )
    token_url_normalisiert = _text_normalisieren(
        token_url
    )

    if endpunkt_normalisiert in profil.endpunkt_aliase:
        endpunkt = profil.standard_endpunkt

    if token_url_normalisiert in profil.token_url_aliase:
        token_url = profil.standard_token_url

    return profil, endpunkt, token_url


def api_key_id_hinweis_fuer_url(url):
    """Liefert den Anbieterhinweis, falls eine Key-ID Pflicht ist."""
    profil = rest_anbieterprofil_fuer_url(url)

    if profil and profil.api_key_id_erforderlich:
        return profil.api_key_id_hinweis

    return ""


def antwort_timeout_fuer_url(url):
    """Liefert ein kompatibles Antwortzeitfenster oder ``None``."""
    profil = rest_anbieterprofil_fuer_url(url)

    if profil is None:
        return None

    return profil.antwort_timeout
