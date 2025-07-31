# promptopilot/views.py

from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import PromptHistory
import logging

logger = logging.getLogger(__name__)


# 🧾 Renders main tool interface (e.g., iframe view)
def ad_builder_page(request):
    return render(request, "promptopilot/ad_builder.html", {
        "STATIC_HOST": "/static/"
    })


# 🧾 Renders alternate widget frame version (optional)
def widget_frame_page(request):
    return render(request, "promptopilot/widget_frame.html", {
        "STATIC_HOST": "/static/"
    })


# ⚙️ Handles prompt POST from iframe or frontend widget
@csrf_exempt  # 🔐 Use with caution — only allow trusted origins in settings
def ad_builder_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed."}, status=405)

    try:
        user_id = request.POST.get("user_id", "anonymous")
        product_name = request.POST.get("product_name", "").strip()
        audience = request.POST.get("audience", "").strip()
        tone = request.POST.get("tone", "").strip()
        model = request.POST.get("model", "").strip()

        # ✅ Validate required fields
        if not product_name or not audience or not tone or not model:
            return JsonResponse({"error": "Missing required fields."}, status=400)
        if len(product_name) > 255:
            return JsonResponse({"error": "Product name too long."}, status=400)
        if len(tone) > 100:
            return JsonResponse({"error": "Tone too long."}, status=400)

        # 🤖 Simulate AI response
        output = (
            f"🚀 Sample ad generated for {product_name} targeting {audience} "
            f"with a {tone} tone using {model}."
        )

        # 💾 Save to PromptHistory with soft delete support
        PromptHistory.objects.create(
            user_id=user_id,
            product_name=product_name,
            audience=audience,
            tone=tone,
            model_used=model,
            result=output,
            is_active=True,
        )

        return JsonResponse({"result": output})

    except Exception as e:
        logger.error(f"[API Error] Failed to handle ad_builder_api: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)


# 📜 View prompt history by user/session ID
def prompt_history_view(request):
    user_id = request.GET.get("user_id", "anonymous")
    history = PromptHistory.objects.filter(user_id=user_id, is_active=True).order_by("-created_at")[:50]

    return render(request, "promptopilot/prompt_history.html", {
        "history": history,
        "user_id": user_id
    })
