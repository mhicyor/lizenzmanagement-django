from django.core.management.base import BaseCommand

from datenintegritaet_service import datenintegritaet_pruefen


class Command(BaseCommand):
    help = "Prüft und repariert sichere Datenbank-Verknüpfungen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reparieren",
            action="store_true",
            help="Entfernt verwaiste Verweise und stellt klare Quellenverknüpfungen wieder her.",
        )

    def handle(self, *args, **options):
        ergebnis = datenintegritaet_pruefen(
            reparieren=bool(options.get("reparieren")),
        )

        self.stdout.write(
            "Fremdschlüsselfehler: "
            f"{ergebnis['fremdschluesselfehler_vorher']} vorher, "
            f"{ergebnis['fremdschluesselfehler_nachher']} nachher."
        )

        eigentum = ergebnis["lizenz_eigentum"]
        self.stdout.write(
            "Lizenzquellen: "
            f"{eigentum['verknuepft']} verknüpft, "
            f"{eigentum['normalisiert']} normalisiert, "
            f"{eigentum['mehrdeutig']} mehrdeutig."
        )

        if not options.get("reparieren"):
            self.stdout.write(
                self.style.WARNING(
                    "Nur geprüft. Mit --reparieren werden sichere Korrekturen angewendet."
                )
            )
        elif ergebnis["fremdschluesselfehler_nachher"] == 0:
            self.stdout.write(
                self.style.SUCCESS("Datenintegrität erfolgreich repariert.")
            )
