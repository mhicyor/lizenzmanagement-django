import os
from dotenv import load_dotenv


load_dotenv()


SYNC_QUELLEN_ENV_KEYS = {
    "ad": [
        "AD_SERVER",
        "AD_PORT",
        "AD_USER",
        "AD_PASSWORD",
        "AD_BASE_DN",
    ],
}


def pruefe_env_key(key):
    wert = os.getenv(key)

    return {
        "key": key,
        "vorhanden": bool(wert and wert.strip()),
    }


def pruefe_sync_konfiguration(quellen_typ):
    benoetigte_keys = SYNC_QUELLEN_ENV_KEYS.get(quellen_typ, [])

    ergebnis = [pruefe_env_key(key) for key in benoetigte_keys]

    fehlende_keys = [
        eintrag["key"]
        for eintrag in ergebnis
        if not eintrag["vorhanden"]
    ]

    return {
        "quellen_typ": quellen_typ,
        "vollstaendig": len(fehlende_keys) == 0 and len(benoetigte_keys) > 0,
        "keys": ergebnis,
        "fehlende_keys": fehlende_keys,
    }
