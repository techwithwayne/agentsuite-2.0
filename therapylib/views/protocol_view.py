from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from therapylib.models import Protocol
from therapylib.serializers.protocol import ProtocolSerializer

class ProtocolViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    /api/therapylib/protocols/                 (list published latest per condition)
    /api/therapylib/protocols/{slug}/          (retrieve latest published by condition.slug)
    """
    serializer_class = ProtocolSerializer
    lookup_field = "slug"

    def get_queryset(self):
        # Latest published per condition
        qs = (
            Protocol.objects
            .filter(published=True)
            .select_related("condition")
            .prefetch_related("items__substance", "items__preparation_form", "items__evidence", "references")
            .order_by("condition__name", "-version")
        )
        return qs

    def list(self, request, *args, **kwargs):
        # Reduce to latest version per condition
        latest = {}
        for p in self.get_queryset():
            key = p.condition_id
            if key not in latest:
                latest[key] = p
        data = self.get_serializer(list(latest.values()), many=True).data
        return Response(data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        slug = kwargs.get(self.lookup_field)
        obj = (
            self.get_queryset()
            .filter(condition__slug=slug)
            .order_by("-version")
            .first()
        )
        obj = get_object_or_404(self.get_queryset(), pk=obj.pk) if obj else get_object_or_404(self.get_queryset(), condition__slug=slug)
        ser = self.get_serializer(obj)
        return Response(ser.data, status=status.HTTP_200_OK)
"""therapylib.views.protocol_view"""

