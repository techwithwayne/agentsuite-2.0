from rest_framework import serializers
from .models import Order

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'id',
            'customer_first_name',
            'customer_last_name',
            'customer_email',
            'pickup_time',
            'order_items',
            'status',
            'created_at'
        ]
