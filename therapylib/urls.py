from django.urls import path, include, re_path
from rest_framework.routers import SimpleRouter
from therapylib.views.monograph_view import MonographViewSet
from therapylib.views.protocol_view import ProtocolViewSet
from therapylib.views.search_view import SearchView
from therapylib.views.handout_pdf_view import HandoutPDFView

router = SimpleRouter()
router.register(r"monographs", MonographViewSet, basename="monograph")
router.register(r"protocols",  ProtocolViewSet,  basename="protocol")

urlpatterns = [
    re_path(r"^search/?$", SearchView.as_view(), name="therapylib-search"),
    path("handouts/<slug:slug>/pdf/", HandoutPDFView.as_view(), name="therapylib-handout-pdf"),
    path("", include(router.urls)),
]
