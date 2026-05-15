"""
Telegram Bot Webhook — Opsiyonel webhook modu için.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

logger = logging.getLogger(__name__)


@csrf_exempt
def telegram_webhook(request, token):
    """Telegram'dan gelen webhook isteklerini işle."""
    if token != settings.TELEGRAM_BOT_TOKEN:
        return JsonResponse({"error": "forbidden"}, status=403)

    if request.method != "POST":
        return JsonResponse({"error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
        logger.info("Webhook update received: %s", body.get("update_id"))
        # Placeholder — webhook modunda bot burada işlenir
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    return JsonResponse({"ok": True})
