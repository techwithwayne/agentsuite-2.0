from rest_framework import generics, status
from rest_framework.response import Response
from .models import Order
from .serializers import OrderSerializer

from .utils import send_order_email_to_owner, send_order_confirmation_to_customer

from django.views import View
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

from django.shortcuts import render

def checkout_success(request):
    return render(request, 'checkout_success.html')

def checkout_cancel(request):
    return render(request, 'checkout_cancel.html')

stripe.api_key = settings.STRIPE_SECRET_KEY  # ✅ Initialize stripe

@csrf_exempt
def stripe_webhook(request):
    print("✅ Stripe webhook called")  # Add this
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        print("⚠️ Invalid payload:", e)
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        print("⚠️ Invalid signature:", e)
        return HttpResponse(status=400)

    print(f"✅ Event received: {event['type']}")  # Add this

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        print(f"✅ Checkout session: {session}")  # Add this

        order_id = session.get('metadata', {}).get('order_id')
        print(f"✅ order_id from metadata: {order_id}")  # Add this

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.status = 'Paid'
                order.save()
                print(f"✅ Order {order_id} marked as Paid.")
            except Order.DoesNotExist:
                print(f"⚠️ Order {order_id} does not exist.")
        else:
            print("⚠️ order_id not found in metadata")

    return HttpResponse(status=200)

def stripe_success_view(request):
    session_id = request.GET.get("session_id")
    print(f"✅ Received session_id: {session_id}")

    order = None

    if session_id:
        try:
            # Try DB first
            order = Order.objects.get(stripe_session_id=session_id)
            print(f"✅ Order found in DB: {order}")
        except Order.DoesNotExist:
            print(f"❌ Order not found with session_id: {session_id}")
            try:
                # Fallback: pull from Stripe API
                session = stripe.checkout.Session.retrieve(session_id)

                # Safer fallback using session details
                customer_email = session.get("metadata", {}).get("customer_email", "unknown@example.com")
                customer_name = session.get("metadata", {}).get("customer_name", "Valued Customer")

                order = {
                    "name": customer_name,
                    "email": customer_email,
                    "pickup_time": session.metadata.get("pickup_time", "N/A"),
                    "menu_item": session.metadata.get("menu_item", "N/A"),
                    "amount": int(session.amount_total) / 100,
                    "fallback": True,
                }

                print(f"🔁 Fallback order reconstructed from session")
            except Exception as e:
                print(f"❌ Stripe fallback failed: {e}")
                order = None

    return render(request, "checkout_success.html", {"order": order})




def get_stripe_publishable_key(request):
    return JsonResponse({
        'publishableKey': settings.STRIPE_PUBLISHABLE_KEY
    })

class CreateCheckoutSessionView(View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            order_id = data.get("order_id")
            order = get_object_or_404(Order, id=order_id)

            line_items = []
            for item in order.order_items:
                line_items.append({
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': item['item']},
                        'unit_amount': int(float(item.get('price', 5.50)) * 100),
                    },
                    'quantity': item.get('quantity', 1),
                })

            session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url=settings.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.STRIPE_CANCEL_URL,
            metadata={
                'order_id': str(order.id),
                'pickup_time': order.pickup_time.strftime("%Y-%m-%d %H:%M"),
                'menu_item': ', '.join(item['item'] for item in order.order_items),
                'customer_name': f"{order.customer_first_name} {order.customer_last_name}",
                'customer_email': order.customer_email,
            },
            customer_email=order.customer_email,
        )


            # ✅ Save session ID to the Order for DB lookup later
            order.stripe_session_id = session.id
            order.save()

            return JsonResponse({'id': session.id})
        except Exception as e:
            print("Stripe Checkout creation error:", str(e))
            return JsonResponse({'error': str(e)}, status=500)


class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def perform_create(self, serializer):
        try:
            print("🧪 Attempting to save order...")
            order = serializer.save()
            print("✅ Order saved:", order)

            send_order_email_to_owner(order)
            send_order_confirmation_to_customer(order)

        except Exception as e:
            print("❌ Error during order creation:")
            import traceback
            traceback.print_exc()
            raise
