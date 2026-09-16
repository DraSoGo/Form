from django.urls import path, include
from django.conf import settings
from core import views
from core.auth import login_view

urlpatterns = [
    path("health", views.health),
    path("login/", login_view),
    path("logout/", views.logout_view),
    path("", include("core.urls")),
    path("manifest.webmanifest", views.manifest),
    path("sw.js", views.service_worker),
]
if "coaching" in settings.INSTALLED_APPS:
    urlpatterns.append(path("coach/", include("coaching.urls")))
