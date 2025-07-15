from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_order_email_to_owner(order):
    subject = f"New Order from {order.customer_first_name} {order.customer_last_name}"
    context = {
        'order': order
    }
    html_message = render_to_string('orders/email_owner_notification.html', context)
    plain_message = strip_tags(html_message)
    send_mail(
        subject,
        plain_message,
        None,  # use DEFAULT_FROM_EMAIL
        ['youremail@example.com'],  # replace with your actual notification email
        html_message=html_message,
    )

def send_order_confirmation_to_customer(order):
    subject = "Your Coffee Order Confirmation"
    context = {
        'order': order
    }
    html_message = render_to_string('orders/email_customer_confirmation.html', context)
    plain_message = strip_tags(html_message)
    send_mail(
        subject,
        plain_message,
        None,
        [order.customer_email],
        html_message=html_message,
    )
