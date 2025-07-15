from django.db import models

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    ]

    customer_first_name = models.CharField(max_length=50, null=True, blank=True)
    customer_last_name = models.CharField(max_length=50, null=True, blank=True)
    customer_email = models.EmailField()
    pickup_time = models.DateTimeField()
    order_items = models.JSONField(help_text="Stores items, quantities, options.")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    stripe_session_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_first_name} {self.customer_last_name} - {self.status}"
