# Stripe Pack Testing Runbook (LIVE)

## Render Shell (Django) — Create a Pack Checkout Session
```bash
python manage.py shell -c "import os, json, stripe, traceback
stripe.api_key = os.environ.get('STRIPE_LIVE_SECRET_KEY') or os.environ.get('STRIPE_SECRET_KEY') or ''
price = os.environ.get('PPA_STRIPE_LIVE_PRICE_ID') or ''
print('price=', price)

try:
    sess = stripe.checkout.Session.create(
        mode='payment',
        line_items=[{'price': price, 'quantity': 1}],
        success_url='https://postpressai.com/payment-complete/?session_id={CHECKOUT_SESSION_ID}',
        cancel_url='https://postpressai.com/payment-cancelled/',
        payment_method_types=['card'],
        metadata={'ppa_kind':'pack','billing_period':'one_time','pack_type':'manual_debug','pack_tokens':'120000','license_key':'PPA-QVFGY-DQUWP-63FQC-F57GN'}
    )
    print('OK', sess.id)
    print('url', sess.url)
except Exception as e:
    print('FAIL', type(e).__name__)
    traceback.print_exc()
    if hasattr(e,'user_message'): print('user_message=', e.user_message)
    if hasattr(e,'json_body') and e.json_body: print('json_body=', json.dumps(e.json_body, indent=2))
"