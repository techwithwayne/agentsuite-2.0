from django.test import TestCase, Client
from therapylib.models import Category, Substance, Monograph

class SynonymSearchTests(TestCase):
    def setUp(self):
        # Minimal valid graph: Category -> Substance -> Monograph
        self.cat = Category.objects.create(name="Supplements")
        self.sub = Substance.objects.create(
            name="Omega-3 Fatty Acids",
            category=self.cat,
            summary="EPA and DHA are key components.",
        )
        self.mono = Monograph.objects.create(substance=self.sub)
        self.client = Client()

    def test_synonym_expansion_fish_oil_finds_omega3(self):
        # "fish oil" expands to include "omega-3", so we should match the substance by name
        resp = self.client.get("/api/therapylib/search/?q=fish%20oil")
        self.assertEqual(resp.status_code, 200, resp.content)

        payload = resp.json()
        self.assertIn("omega-3", payload.get("expanded", []))

        mono_names = [m["substance"]["name"].lower() for m in payload["monographs"]]
        self.assertTrue(any("omega-3" in n for n in mono_names), mono_names)
