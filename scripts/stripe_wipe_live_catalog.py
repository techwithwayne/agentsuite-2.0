#!/usr/bin/env python3
"""
Wipe (deactivate) PostPress live Stripe catalog objects safely.

Strategy:
- Build target Price IDs from env PPA_STRIPE_PRICE_MAP.live (strings beginning with "price_")
- Deactivate Payment Links that reference any target prices
- For each product behind those prices:
    - If product.default_price would be deactivated, try to clear it; if not possible, park it on a temp $0 price
    - Deactivate all active prices for that product
    - Deactivate the product

Notes:
- Stripe doesn't support deleting Products/Prices; "wipe" == active=false. :contentReference[oaicite:5]{index=5}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import stripe


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def flatten_price_ids(obj: Any) -> Set[str]:
    """Recursively collect strings that look like Stripe Price IDs."""
    out: Set[str] = set()
    if isinstance(obj, str):
        if obj.startswith("price_"):
            out.add(obj)
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out |= flatten_price_ids(v)
        return out
    if isinstance(obj, list):
        for v in obj:
            out |= flatten_price_ids(v)
        return out
    return out


def load_target_price_ids_from_env() -> Set[str]:
    raw = os.environ.get("PPA_STRIPE_PRICE_MAP", "") or ""
    if not raw.strip():
        return set()
    try:
        mp = json.loads(raw)
    except Exception as ex:
        raise RuntimeError(f"PPA_STRIPE_PRICE_MAP is not valid JSON: {ex}") from ex

    live_bucket = mp.get("live", {})
    return flatten_price_ids(live_bucket)


def stripe_call_with_backoff(fn, *args, **kwargs):
    """Small retry for transient Stripe errors / rate limits."""
    for attempt in range(1, 6):
        try:
            return fn(*args, **kwargs)
        except stripe.error.RateLimitError as ex:
            sleep_s = 0.5 * attempt
            eprint(f"[rate_limit] sleeping {sleep_s:.1f}s then retrying: {ex}")
            time.sleep(sleep_s)
        except stripe.error.APIConnectionError as ex:
            sleep_s = 0.5 * attempt
            eprint(f"[api_connection] sleeping {sleep_s:.1f}s then retrying: {ex}")
            time.sleep(sleep_s)
    # last try, let it raise
    return fn(*args, **kwargs)


def get_default_price_id(product_obj: stripe.Product) -> Optional[str]:
    dp = getattr(product_obj, "default_price", None)
    if not dp:
        return None
    if isinstance(dp, str):
        return dp
    # expanded object
    return getattr(dp, "id", None)


def try_clear_default_price(product_id: str, apply: bool) -> bool:
    """
    Attempt to clear default_price.

    Stripe products can have default_price = null. :contentReference[oaicite:6]{index=6}
    In practice, some client libs require passing empty string to unset.
    If Stripe rejects it, we return False and caller will "park" default_price.
    """
    if not apply:
        print(f"[dry-run] would try to clear default_price on product {product_id}")
        return True  # assume success for planning; fallbacks still safe

    try:
        stripe_call_with_backoff(stripe.Product.modify, product_id, default_price="")
        return True
    except stripe.error.InvalidRequestError as ex:
        # Typical failure is "cannot be unset" / parameter_invalid_empty
        msg = str(ex)
        eprint(f"[warn] could not clear default_price on {product_id}: {msg}")
        return False


def create_parking_price(product_id: str, currency: str, apply: bool) -> str:
    """
    Create a temporary $0 price used only to hold default_price.

    We keep it simple: one-time 0-unit price.
    """
    if not apply:
        fake_id = "price_PARKING_DRYRUN"
        print(f"[dry-run] would create parking price on product {product_id} currency={currency} -> {fake_id}")
        return fake_id

    price = stripe_call_with_backoff(
        stripe.Price.create,
        product=product_id,
        currency=currency,
        unit_amount=0,
        nickname="PPA PARKING PRICE (auto)",
    )
    return price.id


def set_product_default_price(product_id: str, price_id: str, apply: bool) -> None:
    if not apply:
        print(f"[dry-run] would set product {product_id} default_price -> {price_id}")
        return
    stripe_call_with_backoff(stripe.Product.modify, product_id, default_price=price_id)


def deactivate_price(price_id: str, apply: bool) -> None:
    if not apply:
        print(f"[dry-run] would deactivate price {price_id}")
        return
    stripe_call_with_backoff(stripe.Price.modify, price_id, active=False)


def deactivate_product(product_id: str, apply: bool) -> None:
    if not apply:
        print(f"[dry-run] would deactivate product {product_id}")
        return
    stripe_call_with_backoff(stripe.Product.modify, product_id, active=False)


def payment_link_price_ids(payment_link_id: str) -> Set[str]:
    """
    Fetch full line_items for a Payment Link and collect price IDs.
    Stripe provides a dedicated line_items endpoint. :contentReference[oaicite:7]{index=7}
    """
    ids: Set[str] = set()
    items = stripe_call_with_backoff(stripe.PaymentLink.list_line_items, payment_link_id, limit=100)
    for li in items.auto_paging_iter():
        price = getattr(li, "price", None)
        if isinstance(price, str) and price.startswith("price_"):
            ids.add(price)
        elif price and getattr(price, "id", "").startswith("price_"):
            ids.add(price.id)
    return ids


def deactivate_payment_links(target_price_ids: Set[str], apply: bool) -> List[str]:
    deactivated: List[str] = []
    for pl in stripe_call_with_backoff(stripe.PaymentLink.list, limit=100).auto_paging_iter():
        if not getattr(pl, "active", False):
            continue
        pl_id = pl.id
        try:
            pl_price_ids = payment_link_price_ids(pl_id)
        except Exception as ex:
            eprint(f"[warn] could not read line_items for payment_link {pl_id}: {ex}")
            continue

        if pl_price_ids & target_price_ids:
            if not apply:
                print(f"[dry-run] would deactivate payment link {pl_id} (hits prices: {sorted(pl_price_ids & target_price_ids)})")
            else:
                stripe_call_with_backoff(stripe.PaymentLink.modify, pl_id, active=False)  # :contentReference[oaicite:8]{index=8}
                print(f"[ok] deactivated payment link {pl_id}")
            deactivated.append(pl_id)
    return deactivated


def list_prices_for_product(product_id: str) -> List[stripe.Price]:
    prices = stripe_call_with_backoff(stripe.Price.list, product=product_id, limit=100)
    return list(prices.auto_paging_iter())


def derive_currency(prices: List[stripe.Price]) -> str:
    for p in prices:
        c = getattr(p, "currency", None)
        if isinstance(c, str) and c:
            return c
    return "usd"


def wipe_product_catalog(product_id: str, apply: bool) -> None:
    # Retrieve with expanded default_price (handy when default_price is object)
    prod = stripe_call_with_backoff(stripe.Product.retrieve, product_id, expand=["default_price"])
    prices = list_prices_for_product(product_id)

    active_prices = [p for p in prices if getattr(p, "active", False)]
    default_price_id = get_default_price_id(prod)

    print(f"\n== product {product_id} name={getattr(prod,'name',None)!r} default_price={default_price_id} active_prices={len(active_prices)} ==")

    # If default_price is active, it will block archiving that price.
    # We want to deactivate *all* prices for a "clean" catalog.
    if default_price_id:
        # if default price is active, handle it first
        if any(p.id == default_price_id and p.active for p in active_prices):
            cleared = try_clear_default_price(product_id, apply=apply)
            if not cleared:
                currency = derive_currency(prices)
                parking_price_id = create_parking_price(product_id, currency=currency, apply=apply)
                set_product_default_price(product_id, parking_price_id, apply=apply)
                default_price_id = parking_price_id  # now the default is "parked"

    # Deactivate all active prices EXCEPT current default_price (if any)
    # Then attempt to clear default_price and deactivate the last one too.
    for p in active_prices:
        if default_price_id and p.id == default_price_id:
            continue
        try:
            deactivate_price(p.id, apply=apply)
        except stripe.error.InvalidRequestError as ex:
            # If we hit the default-price blocker anyway, park and retry
            msg = str(ex)
            if "default price of its product" in msg.lower():
                eprint(f"[warn] default-price blocker hit for price {p.id}; parking default_price then retrying")
                currency = derive_currency(prices)
                parking_price_id = create_parking_price(product_id, currency=currency, apply=apply)
                set_product_default_price(product_id, parking_price_id, apply=apply)
                deactivate_price(p.id, apply=apply)
            else:
                raise

    # Now try to clear default_price again and deactivate the last remaining active (if any)
    if default_price_id:
        cleared = try_clear_default_price(product_id, apply=apply)
        if cleared:
            # refresh price list and deactivate anything still active
            prices2 = list_prices_for_product(product_id)
            for p in prices2:
                if getattr(p, "active", False):
                    deactivate_price(p.id, apply=apply)
        else:
            print(f"[warn] leaving parked default_price active for product {product_id} (product will still be deactivated)")

    deactivate_product(product_id, apply=apply)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually mutate Stripe. Omit for dry-run.")
    parser.add_argument("--all-products", action="store_true", help="Ignore PPA_STRIPE_PRICE_MAP and wipe all active products.")
    parser.add_argument("--limit", type=int, default=0, help="Max products to process (0 = no limit).")
    args = parser.parse_args()

    api_key = os.environ.get("STRIPE_LIVE_SECRET_KEY") or os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        eprint("Missing STRIPE_LIVE_SECRET_KEY (preferred) or STRIPE_SECRET_KEY in env.")
        return 2

    stripe.api_key = api_key

    apply = bool(args.apply)
    if not apply:
        print("RUN MODE: dry-run (no Stripe mutations)")
    else:
        print("RUN MODE: APPLY (mutating Stripe LIVE catalog)")

    if args.all_products:
        product_ids: Set[str] = set()
        for prod in stripe_call_with_backoff(stripe.Product.list, limit=100, active=True).auto_paging_iter():
            product_ids.add(prod.id)
            if args.limit and len(product_ids) >= args.limit:
                break

        print(f"Targeting ALL active products: {len(product_ids)}")
        target_price_ids: Set[str] = set()  # used only for payment link filtering; skip in all-products mode
    else:
        target_price_ids = load_target_price_ids_from_env()
        if not target_price_ids:
            eprint("No target prices found in PPA_STRIPE_PRICE_MAP.live. Use --all-products to force.")
            return 3

        print(f"Target prices from PPA_STRIPE_PRICE_MAP.live: {len(target_price_ids)}")

        # Derive products from those prices
        product_ids = set()
        for pid in sorted(target_price_ids):
            try:
                price = stripe_call_with_backoff(stripe.Price.retrieve, pid, expand=["product"])
            except stripe.error.InvalidRequestError as ex:
                eprint(f"[warn] could not retrieve price {pid}: {ex}")
                continue
            prod = getattr(price, "product", None)
            if isinstance(prod, str):
                product_ids.add(prod)
            elif prod and getattr(prod, "id", ""):
                product_ids.add(prod.id)

        if args.limit:
            product_ids = set(list(sorted(product_ids))[: args.limit])

        print(f"Derived products from target prices: {len(product_ids)}")

    # 1) Deactivate payment links that reference targeted prices (safe even if we later wipe products)
    if not args.all_products:
        _ = deactivate_payment_links(target_price_ids, apply=apply)
    else:
        print("Skipping payment link filtering in --all-products mode (you can add it if needed).")

    # 2) Wipe products + prices
    for i, prod_id in enumerate(sorted(product_ids), start=1):
        if args.limit and i > args.limit:
            break
        wipe_product_catalog(prod_id, apply=apply)

    print("\nDONE.")
    if not apply:
        print("Dry-run complete. Re-run with --apply to execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())