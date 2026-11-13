from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from django import template
from django.utils.timezone import localtime

register = template.Library()


@register.filter
def zeitpunkt_lokal(value):
    """SQLite-Zeitpunkte aus UTC in der lokalen Anzeigezeitzone darstellen."""
    if not value:
        return ""
    try:
        zeitpunkt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return ""
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return localtime(zeitpunkt).strftime("%d.%m.%Y · %H:%M")


@register.filter(name="betrag_de")
def betrag_de(value):
    """
    Formatiert einen Geldbetrag im deutschen Zahlenformat.

    Beispiele:
    52877.16 -> 52.877,16
    25200     -> 25.200,00
    None      -> 0,00
    """
    if value in (None, ""):
        value = 0

    try:
        betrag = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value

    englisch_formatiert = f"{betrag:,.2f}"

    return englisch_formatiert.translate(
        str.maketrans({
            ",": ".",
            ".": ",",
        })
    )
