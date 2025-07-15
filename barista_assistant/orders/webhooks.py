import stripe
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY

@csrf_exempt
def stripe_webhook(request):
    from django.views.decorators.csrf import csrf_exempt
    from django.http import HttpResponse
    import stripe
    import json
    from django.conf import settings
    from .models import Order

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    print("✅ Stripe webhook hit")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        print(f"⚠️ Invalid payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        print(f"⚠️ Invalid signature: {e}")
        return HttpResponse(status=400)

    print(f"✅ Received event: {event['type']}")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        order_id = metadata.get('order_id')
        print(f"✅ Found order_id in metadata: {order_id}")

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                print(f"✅ Order fetched: {order}")
                order.status = 'Paid'   # adjust if your model has CHOICES
                order.save()
                print(f"✅ Order {order_id} marked as Paid.")
            except Order.DoesNotExist:
                print(f"⚠️ Order {order_id} does not exist.")
        else:
            print("⚠️ No order_id found in metadata")

    return HttpResponse(status=200)
