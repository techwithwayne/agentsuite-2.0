from django.shortcuts import render
from rest_framework import generics
from .models import MenuItem
from .serializers import MenuItemSerializer

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