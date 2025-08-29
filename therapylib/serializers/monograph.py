from rest_framework import serializers
from django.urls import reverse
from therapylib.models import (
    Monograph, MonographVersion, DoseRange, PreparationForm,
    Substance, Reference, Category
)

class ReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reference
        fields = ("id", "title", "authors", "year", "journal", "doi", "url", "pmid")

class PreparationFormMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreparationForm
        fields = ("id", "name", "slug")

class DoseRangeSerializer(serializers.ModelSerializer):
    form = PreparationFormMiniSerializer()
    class Meta:
        model = DoseRange
        fields = ("id", "form", "amount_min", "amount_max", "unit", "frequency", "duration", "notes")

class MonographVersionSerializer(serializers.ModelSerializer):
    references = ReferenceSerializer(many=True)
    doses = DoseRangeSerializer(many=True)
    class Meta:
        model = MonographVersion
        fields = (
            "id", "version", "created_at", "updated_at",
            "indications", "mechanism", "dosing_overview",
            "contraindications", "interactions", "adverse_effects",
            "pregnancy_lactation", "pediatrics", "geriatrics",
            "lab_markers", "evidence_summary", "notes",
            "references", "doses",
        )

class CategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")

class SubstanceMiniSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer()
    class Meta:
        model = Substance
        fields = ("id", "name", "slug", "category")

class MonographSerializer(serializers.ModelSerializer):
    substance = SubstanceMiniSerializer()
    current_version = MonographVersionSerializer(allow_null=True)
    substance_slug = serializers.CharField(source="substance.slug", read_only=True)
    handout_pdf = serializers.SerializerMethodField()

    class Meta:
        model = Monograph
        fields = ("id", "substance", "substance_slug", "current_version", "handout_pdf")

    def get_handout_pdf(self, obj):
        """
        Returns absolute URLs for patient/practitioner PDFs (inline & download).
        """
        request = self.context.get("request")
        slug = obj.substance.slug
        path = reverse("therapylib-handout-pdf", kwargs={"slug": slug})

        def absu(url_path):
            return request.build_absolute_uri(url_path) if request is not None else url_path

        return {
            "patient": {
                "inline":   absu(f"{path}?mode=patient"),
                "download": absu(f"{path}?mode=patient&download=1"),
            },
            "practitioner": {
                "inline":   absu(f"{path}?mode=practitioner"),
                "download": absu(f"{path}?mode=practitioner&download=1"),
            },
        }
