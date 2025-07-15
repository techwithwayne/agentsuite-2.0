from django.contrib import admin
from .models import StrategyRequest

@admin.register(StrategyRequest)
class StrategyRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'niche', 'tone', 'created_at')
    search_fields = ('niche', 'tone', 'goals')
    list_filter = ('created_at',)
