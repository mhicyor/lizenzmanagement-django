from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.utils.deprecation import MiddlewareMixin

# A positive list also blocks legacy GET endpoints that can sync or delete.
READ_VIEWS = frozenset({
    "home", "lizenzen_startseite", "dashboard", "lizenzen_liste", "lizenz_detail",
    "benutzer_liste", "benutzer_detail", "geraete_liste", "server_liste",
    "synchronisation_uebersicht", "anbieter_liste", "lizenzkategorien",
    "auswertungen", "lizenzbestand", "kostenbericht", "ablaufende_lizenzen",
    "deaktivierte_benutzer", "benutzer_export_pdf", "benutzer_export_csv",
    "deaktivierte_benutzer_export_pdf", "deaktivierte_benutzer_export_csv",
})


class ReadOnlyDemoMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method not in {"GET", "HEAD"}:
            return render(request, "lizenzen/demo_readonly.html", status=403)
        name = request.resolver_match.url_name
        if name == "login":
            return redirect("dashboard")
        if name not in READ_VIEWS:
            return render(request, "lizenzen/demo_readonly.html", status=403)
        request.user = User.objects.get(username="demo")
