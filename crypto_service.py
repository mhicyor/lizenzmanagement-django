import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv


PROJEKTVERZEICHNIS = Path(__file__).resolve().parent
ENV_DATEI = PROJEKTVERZEICHNIS / ".env"

load_dotenv(ENV_DATEI)


class VerschluesselungsFehler(Exception):
    pass


def _fernet_laden() -> Fernet:
    schluessel = os.getenv(
        "REST_API_ENCRYPTION_KEY",
        "",
    ).strip()

    if not schluessel:
        raise VerschluesselungsFehler(
            "REST_API_ENCRYPTION_KEY fehlt."
        )

    try:
        return Fernet(
            schluessel.encode("utf-8")
        )
    except (TypeError, ValueError) as fehler:
        raise VerschluesselungsFehler(
            "Der Verschlüsselungsschlüssel ist ungültig."
        ) from fehler


def verschluesseln(
    daten: dict[str, Any],
) -> str:
    if not isinstance(daten, dict):
        raise VerschluesselungsFehler(
            "Es kann nur ein Dictionary verschlüsselt werden."
        )

    try:
        json_text = json.dumps(
            daten,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as fehler:
        raise VerschluesselungsFehler(
            "Die Daten konnten nicht als JSON verarbeitet werden."
        ) from fehler

    token = _fernet_laden().encrypt(
        json_text.encode("utf-8")
    )

    return token.decode("utf-8")


def entschluesseln(
    token: str | None,
) -> dict[str, Any]:
    token = str(token or "").strip()

    if not token:
        return {}

    try:
        entschluesselt = _fernet_laden().decrypt(
            token.encode("utf-8")
        )
    except InvalidToken as fehler:
        raise VerschluesselungsFehler(
            "Die Zugangsdaten konnten nicht entschlüsselt werden."
        ) from fehler

    try:
        daten = json.loads(
            entschluesselt.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as fehler:
        raise VerschluesselungsFehler(
            "Die entschlüsselten Daten sind ungültig."
        ) from fehler

    if not isinstance(daten, dict):
        raise VerschluesselungsFehler(
            "Die entschlüsselten Daten haben ein falsches Format."
        )

    return daten