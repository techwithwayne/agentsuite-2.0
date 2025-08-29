from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from therapylib.models import Monograph
from therapylib.serializers.monograph import MonographSerializer

class MonographViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    /api/therapylib/monographs/               (list)
    /api/therapylib/monographs/{slug}/        (retrieve by substance.slug)
    """
    serializer_class = MonographSerializer

    def get_queryset(self):
        return (
            Monograph.objects
            .select_related("substance", "current_version", "substance__category")
            .prefetch_related("current_version__doses__form", "current_version__references")
        )

    # Allow lookup by the related Substance slug
    lookup_field = "slug"

    def retrieve(self, request, *args, **kwargs):
        slug = kwargs.get(self.lookup_field)
        obj = get_object_or_404(self.get_queryset(), substance__slug=slug)
        ser = self.get_serializer(obj)
        return Response(ser.data, status=status.HTTP_200_OK)
"""therapylib.views.monograph_view"""

