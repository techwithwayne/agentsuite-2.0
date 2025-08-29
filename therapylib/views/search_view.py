import logging
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from therapylib.models import Monograph, Protocol
from therapylib.utils.synonyms import expand_query
from therapylib.serializers.monograph import MonographSerializer
from therapylib.serializers.protocol import ProtocolSerializer

logger = logging.getLogger(__name__)

class SearchView(APIView):
    """
    GET /api/therapylib/search?q=term
    Returns monographs and the latest published protocol per condition that match the query.
    Now synonym-aware via therapylib.utils.synonyms.expand_query().
    """
    def get(self, request, *args, **kwargs):
        q = (request.GET.get("q") or "").strip()

        # If no query, return empty result sets
        if not q:
            return Response(
                {"q": q, "expanded": [], "monographs": [], "protocols": []},
                status=status.HTTP_200_OK
            )

        # Expand synonyms (e.g., "fish oil" -> ["fish oil","omega-3","epa","dha"])
        expanded_terms = expand_query(q)

        if len(expanded_terms) > 1:
            logger.info(
                "search_synonyms",
                extra={"event": "search_synonyms", "original": q, "expanded": expanded_terms}
            )

        # ---- Monographs: match against Substance fields (name/slug/summary) ----
        monograph_filter = Q()
        for term in expanded_terms:
            monograph_filter |= (
                Q(substance__name__icontains=term) |
                Q(substance__slug__icontains=term) |
                Q(substance__summary__icontains=term)
            )

        monographs = (
            Monograph.objects.select_related("substance", "current_version")
            .filter(monograph_filter)
            .order_by("substance__name")[:10]
        )

        # ---- Protocols: match against Condition + protocol summary; return latest per condition ----
        protocol_filter = Q()
        for term in expanded_terms:
            protocol_filter |= (
                Q(condition__name__icontains=term) |
                Q(condition__slug__icontains=term) |
                Q(summary__icontains=term)
            )

        prot_qs = (
            Protocol.objects.select_related("condition")
            .filter(protocol_filter, published=True)
            .order_by("condition_id", "-version")
        )

        # Deduplicate: keep latest version per condition
        latest_by_condition = {}
        for p in prot_qs:
            cur = latest_by_condition.get(p.condition_id)
            if cur is None or p.version > cur.version:
                latest_by_condition[p.condition_id] = p
        protocols = list(latest_by_condition.values())[:10]

        return Response(
            {
                "q": q,
                "expanded": expanded_terms,
                "monographs": MonographSerializer(monographs, many=True).data,
                "protocols": ProtocolSerializer(protocols, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
