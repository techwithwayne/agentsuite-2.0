from rest_framework import serializers
from django.urls import reverse
from therapylib.models import (
    Protocol, ProtocolItem, EvidenceTag, PreparationForm, Substance, Condition, Reference
)

class EvidenceTagMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenceTag
        fields = ("id", "name", "weight")

class PrepFormMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreparationForm
        fields = ("id", "name", "slug")

class SubstanceMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Substance
        fields = ("id", "name", "slug")

class ProtocolItemSerializer(serializers.ModelSerializer):
    # Can be NULL in DB → allow_null=True
    evidence = EvidenceTagMiniSerializer(allow_null=True)
    preparation_form = PrepFormMiniSerializer(allow_null=True)
    substance = SubstanceMiniSerializer()
    handout_pdf = serializers.SerializerMethodField()

    class Meta:
        model = ProtocolItem
        fields = (
            "id", "tier", "substance", "preparation_form",
            "dose_text", "duration", "rationale", "evidence",
            "sort_order", "handout_pdf",
        )

    def get_handout_pdf(self, obj):
        """
        Patient/practitioner PDF links for this item's substance.
        """
        request = self.context.get("request")
        slug = obj.substance.slug
        path = reverse("therapylib-handout-pdf", kwargs={"slug": slug})
        to_abs = (lambda p: request.build_absolute_uri(p)) if request else (lambda p: p)
        return {
            "patient": {
                "inline":   to_abs(f"{path}?mode=patient"),
                "download": to_abs(f"{path}?mode=patient&download=1"),
            },
            "practitioner": {
                "inline":   to_abs(f"{path}?mode=practitioner"),
                "download": to_abs(f"{path}?mode=practitioner&download=1"),
            },
        }

class ReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reference
        fields = ("id", "title", "authors", "year", "journal", "doi", "url", "pmid")

class ConditionMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Condition
        fields = ("id", "name", "slug")

class ProtocolSerializer(serializers.ModelSerializer):
    condition = ConditionMiniSerializer()
    # Pass request context so nested items can build absolute URLs
    items = ProtocolItemSerializer(many=True)
    references = ReferenceSerializer(many=True)

    class Meta:
        model = Protocol
        fields = ("id", "condition", "version", "summary", "published", "created_at", "items", "references")
