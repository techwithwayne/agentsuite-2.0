from django.contrib import admin
from .models import Order

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_first_name', 'customer_last_name', 'pickup_time', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('customer_first_name', 'customer_last_name', 'customer_email')
    readonly_fields = ('created_at',)