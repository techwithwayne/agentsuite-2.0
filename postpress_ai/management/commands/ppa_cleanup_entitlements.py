# /home/techwithwayne/agentsuite/postpress_ai/management/commands/ppa_cleanup_entitlements.py
"""One-time cleanup: enforce exactly ONE active Entitlement per customer.

Usage:
  # dry-run (default)
  python manage.py ppa_cleanup_entitlements

  # commit changes
  python manage.py ppa_cleanup_entitlements --commit

  # only one customer (email or id)
  python manage.py ppa_cleanup_entitlements --customer you@example.com --commit
  python manage.py ppa_cleanup_entitlements --customer 123 --commit

Rules (safe + minimal):
- For each customer with >1 active Entitlement:
  - Keep ONE entitlement:
      1) prefer entitlements that already have a license linked
      2) then newest by (updated_at, created_at, id)
  - If kept entitlement has no license but another active one does, copy the license to the kept entitlement.
  - Mark all other active entitlements as canceled.
- Does NOT delete rows.
- Does NOT redesign schema.

This exists because historical data may contain multiple active entitlements per customer.
"""

from __future__ import annotations

from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone


class Command(BaseCommand):
    help = "Deactivate duplicate active entitlements so each customer has exactly one active entitlement."  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Apply changes (default is dry-run).",
        )
        parser.add_argument(
            "--customer",
            type=str,
            default="",
            help="Limit to a specific customer (email or numeric id).",
        )

    def handle(self, *args, **options):
        commit: bool = bool(options.get("commit"))
        customer_raw: str = (options.get("customer") or "").strip()

        from postpress_ai.models.customer import Customer
        from postpress_ai.models.entitlement import Entitlement

        active = Entitlement.STATUS_ACTIVE
        canceled = Entitlement.STATUS_CANCELED

        customer_filter = Q()
        if customer_raw:
            if customer_raw.isdigit():
                customer_filter = Q(id=int(customer_raw))
            else:
                customer_filter = Q(email__iexact=customer_raw)

        customers = Customer.objects.all()
        if customer_filter.children:
            customers = customers.filter(customer_filter)

        # Find customers with duplicate active entitlements
        dup_customer_ids = (
            Entitlement.objects.filter(status=active, customer__in=customers)
            .values("customer_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .values_list("customer_id", flat=True)
        )

        dup_ids = list(dup_customer_ids)
        if not dup_ids:
            self.stdout.write(self.style.SUCCESS("No customers with duplicate active entitlements."))
            return

        self.stdout.write(
            f"Found {len(dup_ids)} customer(s) with >1 active entitlement. Mode={'COMMIT' if commit else 'DRY-RUN'}."
        )

        changed_total = 0
        customers_touched = 0

        @transaction.atomic
        def _process_customer(customer_id: int) -> int:
            nonlocal customers_touched

            ents = list(
                Entitlement.objects.filter(customer_id=customer_id, status=active)
                .select_related("license")
                .order_by("-updated_at", "-created_at", "-id")
            )
            if len(ents) <= 1:
                return 0

            # Choose keep: license-linked first, then newest.
            keep = None
            for ent in ents:
                if getattr(ent, "license_id", None):
                    keep = ent
                    break
            if keep is None:
                keep = ents[0]

            # If keep has no license but another does, copy.
            copied_license_id: Optional[int] = None
            if not getattr(keep, "license_id", None):
                for ent in ents:
                    if getattr(ent, "license_id", None):
                        keep.license_id = ent.license_id
                        copied_license_id = ent.license_id
                        break

            # Cancel the rest.
            to_cancel = [e for e in ents if e.id != keep.id]

            if not commit:
                # Dry-run summary
                self.stdout.write(
                    f"- customer_id={customer_id} keep_entitlement_id={keep.id} cancel={[e.id for e in to_cancel]}"
                    + (f" (copied_license_id={copied_license_id})" if copied_license_id else "")
                )
                return len(to_cancel)

            # COMMIT
            now = timezone.now().isoformat()
            if copied_license_id:
                try:
                    meta = keep.meta or {}
                    meta["cleanup"] = {
                        "at": now,
                        "reason": "dedupe_active_entitlements",
                        "copied_license_id": copied_license_id,
                    }
                    keep.meta = meta
                except Exception:
                    pass
                keep.save(update_fields=["license", "meta", "updated_at"])

            n = 0
            for ent in to_cancel:
                ent.status = canceled
                try:
                    meta = ent.meta or {}
                    meta["cleanup"] = {
                        "at": now,
                        "reason": "dedupe_active_entitlements",
                        "kept_entitlement_id": keep.id,
                    }
                    ent.meta = meta
                except Exception:
                    pass
                ent.save(update_fields=["status", "meta", "updated_at"])
                n += 1

            customers_touched += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"- customer_id={customer_id} kept={keep.id} canceled={[e.id for e in to_cancel]}"
                    + (f" (copied_license_id={copied_license_id})" if copied_license_id else "")
                )
            )
            return n

        for cid in dup_ids:
            changed_total += _process_customer(int(cid))

        # Final sanity check (in commit mode)
        if commit:
            still_dups = (
                Entitlement.objects.filter(status=active, customer_id__in=dup_ids)
                .values("customer_id")
                .annotate(n=Count("id"))
                .filter(n__gt=1)
                .count()
            )
            if still_dups:
                self.stdout.write(self.style.WARNING(f"WARNING: {still_dups} customer(s) still have duplicate active entitlements."))
            else:
                self.stdout.write(self.style.SUCCESS("Sanity check OK: no duplicate active entitlements remain for processed customers."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Entitlements deactivated={changed_total}. Customers touched={customers_touched}. Mode={'COMMIT' if commit else 'DRY-RUN'}."
            )
        )
