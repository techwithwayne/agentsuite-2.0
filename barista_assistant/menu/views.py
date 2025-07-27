from django.shortcuts import render
from django.http import JsonResponse
from rest_framework import generics
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import MenuItem
from .serializers import MenuItemSerializer

@csrf_exempt
def seed_menu(request):
    if request.method not in ["GET", "POST"]:
        return JsonResponse({"error": "Only GET or POST allowed."}, status=405)

    sample_items = [
        {"name": "Espresso", "price": 2.50, "description": "Strong and bold shot."},
        {"name": "Latte", "price": 3.50, "description": "Smooth blend of espresso and milk."},
        {"name": "Cappuccino", "price": 3.25, "description": "Frothy delight with milk foam."},
        {"name": "Mocha", "price": 4.00, "description": "Chocolate, coffee, and magic."},
        {"name": "Americano", "price": 2.75, "description": "Espresso with hot water."},
    ]

    created_items = []
    for item in sample_items:
        obj, created = MenuItem.objects.get_or_create(name=item["name"], defaults=item)
        if created:
            created_items.append(obj.name)

    return JsonResponse({
        "status": "success",
        "message": f"Seeded {len(created_items)} new items.",
        "items": created_items
    })

# API View: Returns JSON of all available menu items
class MenuItemListView(generics.ListAPIView):
    queryset = MenuItem.objects.filter(is_available=True)
    serializer_class = MenuItemSerializer

# Template View: Renders menu page using base template
def menu_list(request):
    items = MenuItem.objects.filter(is_available=True)
    return render(request, 'menu/menu_list.html', {'menu_items': items})

def barista_assistant_test(request):
    return render(request, 'menu/barista_assistant_test.html')