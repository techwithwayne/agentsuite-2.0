from decimal import Decimal as D
from django.core.management.base import BaseCommand
from therapylib.models import (
    Category, PreparationForm, EvidenceTag, Reference,
    Substance, Monograph, MonographVersion, DoseRange,
    Condition, Protocol, ProtocolItem,
)

class Command(BaseCommand):
    help = "Seed therapylib with sample data. Idempotent — safe to run multiple times."

    def handle(self, *args, **opts):
        # Categories / Forms / Evidence
        cat_herb, _ = Category.objects.get_or_create(name="Herb")
        cat_vit, _  = Category.objects.get_or_create(name="Vitamin")
        cat_nutr, _ = Category.objects.get_or_create(name="Nutraceutical")

        form_caps, _ = PreparationForm.objects.get_or_create(name="Capsule")
        form_tinc, _ = PreparationForm.objects.get_or_create(name="Tincture")
        form_powd, _ = PreparationForm.objects.get_or_create(name="Powder")
        form_tea,  _ = PreparationForm.objects.get_or_create(name="Tea")

        evA, _ = EvidenceTag.objects.get_or_create(name="A", defaults={"weight": 100})
        evB, _ = EvidenceTag.objects.get_or_create(name="B", defaults={"weight": 50})
        evC, _ = EvidenceTag.objects.get_or_create(name="C", defaults={"weight": 10})

        # References
        ref_berb, _ = Reference.objects.get_or_create(
            title="Berberine and IBS-D outcomes", year=2020, journal="Phytomedicine"
        )
        ref_mg, _ = Reference.objects.get_or_create(
            title="Magnesium for sleep quality", year=2019, journal="Nutrients"
        )
        ref_ash, _ = Reference.objects.get_or_create(
            title="Ashwagandha for anxiety — RCT", year=2021, journal="JAMA Netw Open"
        )

        # Substances
        berb, _ = Substance.objects.get_or_create(
            name="Berberine", category=cat_herb, defaults={"synonyms": ["Berberis", "Coptis extract"]}
        )
        berb.forms.add(form_caps, form_tinc)

        mg_glyc, _ = Substance.objects.get_or_create(
            name="Magnesium Glycinate", category=cat_vit, defaults={"synonyms": ["Magnesium Bisglycinate"]}
        )
        mg_glyc.forms.add(form_caps, form_powd)

        ashw, _ = Substance.objects.get_or_create(
            name="Ashwagandha", category=cat_herb, defaults={"synonyms": ["Withania somnifera"]}
        )
        ashw.forms.add(form_caps, form_tinc)

        # Monograph Versions + Doses (create if none exist)
        def ensure_mv(substance, refs, dose_specs, text_overrides=None):
            current = MonographVersion.objects.filter(substance=substance).order_by("-version").first()
            if current is None:
                current = MonographVersion.objects.create(
                    substance=substance,
                    version=1,
                    indications=(text_overrides or {}).get("indications", ""),
                    mechanism=(text_overrides or {}).get("mechanism", ""),
                    dosing_overview=(text_overrides or {}).get("dosing_overview", ""),
                    contraindications=(text_overrides or {}).get("contraindications", ""),
                    interactions=(text_overrides or {}).get("interactions", ""),
                    adverse_effects=(text_overrides or {}).get("adverse_effects", ""),
                    pregnancy_lactation=(text_overrides or {}).get("pregnancy_lactation", ""),
                    pediatrics=(text_overrides or {}).get("pediatrics", ""),
                    geriatrics=(text_overrides or {}).get("geriatrics", ""),
                    lab_markers=(text_overrides or {}).get("lab_markers", ""),
                    evidence_summary=(text_overrides or {}).get("evidence_summary", ""),
                    notes=(text_overrides or {}).get("notes", ""),
                )
                for r in refs:
                    current.references.add(r)
                for spec in dose_specs:
                    DoseRange.objects.get_or_create(
                        monograph_version=current,
                        form=spec["form"],
                        unit=spec["unit"],
                        defaults=dict(
                            amount_min=spec.get("min"),
                            amount_max=spec.get("max"),
                            frequency=spec.get("freq", ""),
                            duration=spec.get("dur", ""),
                            notes=spec.get("notes", ""),
                        ),
                    )
            mono, _ = Monograph.objects.get_or_create(substance=substance)
            if not mono.current_version:
                mono.current_version = current
                mono.save()
            return current

        # Berberine
        ensure_mv(
            berb,
            refs=[ref_berb],
            dose_specs=[
                {"form": form_caps, "min": D("500"), "max": D("1000"), "unit": "mg", "freq": "BID", "dur": "8–12 weeks"},
                {"form": form_tinc, "min": D("0.5"), "max": D("1.0"), "unit": "mL", "freq": "TID"},
            ],
            text_overrides={
                "indications": "IBS-D, SIBO; metabolic support.",
                "dosing_overview": "Common: 500 mg twice daily; titrate by response.",
                "evidence_summary": "Multiple RCTs for GI/metabolic endpoints.",
            },
        )

        # Magnesium Glycinate
        ensure_mv(
            mg_glyc,
            refs=[ref_mg],
            dose_specs=[
                {"form": form_caps, "min": D("200"), "max": D("400"), "unit": "mg", "freq": "HS", "notes": "Elemental Mg"},
                {"form": form_powd, "min": D("200"), "max": D("400"), "unit": "mg", "freq": "HS"},
            ],
            text_overrides={
                "indications": "Insomnia, restless sleep, muscle tension.",
                "dosing_overview": "200–400 mg elemental Mg at bedtime.",
                "evidence_summary": "Systematic reviews suggest benefit for sleep quality.",
            },
        )

        # Ashwagandha
        ensure_mv(
            ashw,
            refs=[ref_ash],
            dose_specs=[
                {"form": form_caps, "min": D("300"), "max": D("600"), "unit": "mg", "freq": "BID"},
                {"form": form_tinc, "min": D("2"), "max": D("4"), "unit": "mL", "freq": "BID"},
            ],
            text_overrides={
                "indications": "Anxiety, stress, sleep onset.",
                "dosing_overview": "300–600 mg extract twice daily.",
                "evidence_summary": "Multiple RCTs show reduced anxiety scores.",
            },
        )

        # Conditions + Protocols (latest published)
        cond_ibs, _ = Condition.objects.get_or_create(name="IBS-D", defaults={"aliases": ["Irritable bowel syndrome — diarrhea predominant"]})
        cond_anx, _ = Condition.objects.get_or_create(name="Anxiety")
        cond_ins, _ = Condition.objects.get_or_create(name="Insomnia")

        prot_ibs, _ = Protocol.objects.get_or_create(condition=cond_ibs, version=1, defaults={"summary": "First-line and adjuncts", "published": True})
        ProtocolItem.objects.get_or_create(
            protocol=prot_ibs, tier=ProtocolItem.TIER_FIRST, substance=berb, preparation_form=form_caps,
            defaults={"dose_text": "500 mg BID", "rationale": "Best evidence for GI symptoms", "evidence": evA, "sort_order": 1}
        )

        prot_anx, _ = Protocol.objects.get_or_create(condition=cond_anx, version=1, defaults={"summary": "Reduce anxiety and improve sleep", "published": True})
        ProtocolItem.objects.get_or_create(
            protocol=prot_anx, tier=ProtocolItem.TIER_FIRST, substance=ashw, preparation_form=form_caps,
            defaults={"dose_text": "300–600 mg BID", "rationale": "Multiple RCTs reduce anxiety", "evidence": evA, "sort_order": 1}
        )

        prot_ins, _ = Protocol.objects.get_or_create(condition=cond_ins, version=1, defaults={"summary": "Sleep onset/maintenance support", "published": True})
        ProtocolItem.objects.get_or_create(
            protocol=prot_ins, tier=ProtocolItem.TIER_FIRST, substance=mg_glyc, preparation_form=form_caps,
            defaults={"dose_text": "200–400 mg HS", "rationale": "Sleep quality support", "evidence": evB, "sort_order": 1}
        )

        self.stdout.write(self.style.SUCCESS("therapylib seed complete."))
