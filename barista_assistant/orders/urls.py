from django.urls import path
from .views import (
    OrderCreateView,
    CreateCheckoutSessionView,
    stripe_webhook,
    get_stripe_publishable_key,
    stripe_success_view, 
    checkout_cancel,
)
from .webhooks import stripe_webhook

urlpatterns = [
    path('order/', OrderCreateView.as_view(), name='order-create'),
    path('create-checkout-session/', CreateCheckoutSessionView.as_view(), name='create-checkout-session'),
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    path('stripe/publishable-key/', get_stripe_publishable_key, name='stripe-publishable-key'), 
    path('success/', stripe_success_view, name='stripe-success'),
    path('cancel/', checkout_cancel, name='checkout-cancel'),
]
