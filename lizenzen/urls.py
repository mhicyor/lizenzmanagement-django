from django.urls import path
from . import views
from . import team_views


urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.startseite, name="lizenzen_startseite"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("team/", team_views.team_verwalten, name="team_verwalten"),
    path(
        "team/<int:user_id>/loeschen/",
        team_views.benutzer_loeschen,
        name="team_benutzer_loeschen",
    ),
    path(
        "team/<int:user_id>/superuser/",
        team_views.benutzer_zum_superuser_machen,
        name="team_benutzer_zum_superuser_machen",
    ),
    path(
        "profil/",
        team_views.profil_bearbeiten,
        name="profil_bearbeiten",
    ),

    # Synchronisation / Datenquellen
    path(
        "synchronisation/",
        views.synchronisation_uebersicht,
        name="synchronisation_uebersicht"
    ),
    path(
        "synchronisation/hinzufuegen/",
        views.synchronisation_hinzufuegen_view,
        name="synchronisation_hinzufuegen"
    ),
    path(
        "synchronisation/hinzufuegen/rest-api/",
        views.synchronisation_rest_api_hinzufuegen_view,
        name="synchronisation_rest_api_hinzufuegen"
    ),
    path(
        "synchronisation/hinzufuegen/csv/",
        views.synchronisation_csv_hinzufuegen_view,
        name="synchronisation_csv_hinzufuegen"
    ),
    path(
        "synchronisation/csv/<int:datenquelle_id>/bearbeiten/",
        views.csv_datenquelle_bearbeiten_view,
        name="csv_datenquelle_bearbeiten"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/bearbeiten/",
        views.synchronisation_rest_api_hinzufuegen_view,
        name="datenquelle_bearbeiten"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/automatik/",
        views.datenquelle_automatik_view,
        name="datenquelle_automatik"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/deaktivieren/",
        views.datenquelle_deaktivieren_view,
        name="datenquelle_deaktivieren"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/reaktivieren/",
        views.datenquelle_reaktivieren_view,
        name="datenquelle_reaktivieren"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/loeschen/",
        views.datenquelle_loeschen_view,
        name="datenquelle_loeschen"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/synchronisieren/",
        views.datenquelle_synchronisieren_view,
        name="datenquelle_synchronisieren"
    ),
    path(
        "synchronisation/<int:datenquelle_id>/lizenzprodukte/",
        views.datenquelle_lizenzprodukte_view,
        name="datenquelle_lizenzprodukte"
    ),
    path(
        "synchronisation/ad/",
        views.ad_synchronisation,
        name="ad_synchronisation"
    ),

    # Benutzer
    path("benutzer/", views.benutzer_liste, name="benutzer_liste"),
    path(
        "benutzer/export/pdf/",
        views.benutzer_export_pdf,
        name="benutzer_export_pdf",
    ),
    path(
        "benutzer/export/csv/",
        views.benutzer_export_csv,
        name="benutzer_export_csv",
    ),
    path("benutzer/<int:benutzer_id>/", views.benutzer_detail, name="benutzer_detail"),
    path("benutzer/hinzufuegen/", views.benutzer_hinzufuegen_view, name="benutzer_hinzufuegen"),
    path(
        "benutzer/<int:benutzer_id>/lizenz/<int:lizenz_id>/entfernen/",
        views.lizenzzuweisung_entfernen,
        name="lizenzzuweisung_entfernen"
    ),

    # Lizenzkategorien
    path(
        "kategorien/",
        views.lizenzkategorien_view,
        name="lizenzkategorien"
    ),
    path(
        "lizenzkategorien/hinzufuegen/",
        views.lizenzkategorie_hinzufuegen_view,
        name="lizenzkategorie_hinzufuegen"
    ),
    path(
        "lizenzkategorien/<int:kategorie_id>/bearbeiten/",
        views.lizenzkategorie_bearbeiten_view,
        name="lizenzkategorie_bearbeiten"
    ),
    path(
        "lizenzkategorien/<int:kategorie_id>/deaktivieren/",
        views.lizenzkategorie_deaktivieren_view,
        name="lizenzkategorie_deaktivieren"
    ),
    path(
        "lizenzkategorien/<int:kategorie_id>/reaktivieren/",
        views.lizenzkategorie_reaktivieren_view,
        name="lizenzkategorie_reaktivieren"
    ),
    path(
        "lizenzkategorien/<int:kategorie_id>/loeschen/",
        views.lizenzkategorie_loeschen_view,
        name="lizenzkategorie_loeschen"
    ),

    # Anbieter
    path(
        "anbieter/",
        views.anbieter_liste_view,
        name="anbieter_liste"
    ),
    path(
        "anbieter/hinzufuegen/",
        views.anbieter_hinzufuegen_view,
        name="anbieter_hinzufuegen"
    ),
    path(
        "anbieter/<int:anbieter_id>/bearbeiten/",
        views.anbieter_bearbeiten_view,
        name="anbieter_bearbeiten"
    ),
    path(
        "anbieter/<int:anbieter_id>/deaktivieren/",
        views.anbieter_deaktivieren_view,
        name="anbieter_deaktivieren"
    ),
    path(
        "anbieter/<int:anbieter_id>/reaktivieren/",
        views.anbieter_reaktivieren_view,
        name="anbieter_reaktivieren"
    ),
    path(
        "anbieter/<int:anbieter_id>/loeschen/",
        views.anbieter_loeschen_view,
        name="anbieter_loeschen"
    ),

    # Lizenzen
    path("lizenzen/", views.lizenzen_liste, name="lizenzen_liste"),
    path("lizenzen/hinzufuegen/", views.lizenz_hinzufuegen_view, name="lizenz_hinzufuegen"),
    path("lizenzen/zuweisen/", views.lizenz_zuweisen, name="lizenz_zuweisen"),
    path("lizenzen/adobe-import/", views.adobe_import, name="adobe_import"),
    path("lizenzen/assistent/", views.lizenz_assistent_view, name="lizenz_assistent"),

    path(
        "lizenzen/<int:lizenz_id>/<str:ziel_typ>/<int:ziel_id>/entfernen/",
        views.lizenz_zuweisung_entfernen_view,
        name="lizenz_zuweisung_entfernen"
    ),

    path(
        "lizenzen/<int:lizenz_id>/loeschen/",
        views.lizenz_loeschen_view,
        name="lizenz_loeschen"
    ),
    path(
        "lizenzen/<int:lizenz_id>/bearbeiten/",
        views.lizenz_bearbeiten_view,
        name="lizenz_bearbeiten"
    ),
    path(
        "lizenzen/<int:lizenz_id>/server-zuweisen/",
        views.server_lizenz_zuweisen,
        name="server_lizenz_zuweisen"
    ),
    path(
        "lizenzen/<int:lizenz_id>/geraet-zuweisen/",
        views.geraet_lizenz_zuweisen,
        name="geraet_lizenz_zuweisen"
    ),
    path(
        "lizenzen/<int:lizenz_id>/",
        views.lizenz_detail,
        name="lizenz_detail"
    ),

    # Geräte
    path("geraete/", views.geraete_liste, name="geraete_liste"),
    path("geraete/hinzufuegen/", views.geraet_hinzufuegen_view, name="geraet_hinzufuegen"),
    path("geraete/<int:geraet_id>/bearbeiten/", views.geraet_bearbeiten_view, name="geraet_bearbeiten"),
    path("geraete/<int:geraet_id>/loeschen/", views.geraet_loeschen_view, name="geraet_loeschen"),

    # Server
    path("server/", views.server_liste, name="server_liste"),
    path("server/hinzufuegen/", views.server_hinzufuegen_view, name="server_hinzufuegen"),
    path("server/<int:server_id>/bearbeiten/", views.server_bearbeiten_view, name="server_bearbeiten"),
    path("server/<int:server_id>/loeschen/", views.server_loeschen_view, name="server_loeschen"),

    # Auswertungen
    path("auswertungen/", views.auswertungen, name="auswertungen"),
    path("auswertungen/lizenzbestand/", views.lizenzbestand, name="lizenzbestand"),
    path("auswertungen/kostenbericht/", views.kostenbericht, name="kostenbericht"),
    path("auswertungen/ablaufende-lizenzen/", views.ablaufende_lizenzen, name="ablaufende_lizenzen"),
    path("auswertungen/deaktivierte-benutzer/", views.deaktivierte_benutzer, name="deaktivierte_benutzer"),
    path(
        "auswertungen/deaktivierte-benutzer/export/pdf/",
        views.deaktivierte_benutzer_export_pdf,
        name="deaktivierte_benutzer_export_pdf",
    ),
    path(
        "auswertungen/deaktivierte-benutzer/export/csv/",
        views.deaktivierte_benutzer_export_csv,
        name="deaktivierte_benutzer_export_csv",
    ),
]
