from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/ui", permanent=False)),
    path("", include("api.urls")),
]
