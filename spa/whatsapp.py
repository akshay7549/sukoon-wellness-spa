
import requests

from django.conf import settings


# =========================================================
# WHATSAPP MESSAGE SERVICE
# =========================================================

def send_whatsapp_message(phone, message):
    """
    Send a WhatsApp text message.

    Returns:
        dict containing success status and API response.
    """

    # -----------------------------------------------------
    # WhatsApp disabled
    # -----------------------------------------------------

    if not settings.WHATSAPP_ENABLED:
        return {
            "success": False,
            "status": "disabled",
            "message": "WhatsApp integration is disabled.",
        }

    # -----------------------------------------------------
    # Configuration validation
    # -----------------------------------------------------

    if not settings.WHATSAPP_API_URL:
        return {
            "success": False,
            "status": "not_configured",
            "message": "WhatsApp API URL is not configured.",
        }

    if not settings.WHATSAPP_ACCESS_TOKEN:
        return {
            "success": False,
            "status": "not_configured",
            "message": "WhatsApp access token is not configured.",
        }

    # -----------------------------------------------------
    # Phone number cleanup
    # -----------------------------------------------------

    phone = str(phone).strip()

    # India number handling
    if phone.startswith("+"):
        phone = phone[1:]

    if phone.startswith("0"):
        phone = "91" + phone[1:]

    if len(phone) == 10:
        phone = "91" + phone

    # -----------------------------------------------------
    # Headers
    # -----------------------------------------------------

    headers = {
        "Authorization": (
            f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

    # -----------------------------------------------------
    # Request payload
    # -----------------------------------------------------

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message,
        },
    }

    # -----------------------------------------------------
    # API request
    # -----------------------------------------------------

    try:

        response = requests.post(
            settings.WHATSAPP_API_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )

        # -------------------------------------------------
        # Successful response
        # -------------------------------------------------

        if response.ok:

            try:
                response_data = response.json()
            except ValueError:
                response_data = {}

            return {
                "success": True,
                "status": "sent",
                "response": response_data,
            }

        # -------------------------------------------------
        # API error
        # -------------------------------------------------

        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text

        return {
            "success": False,
            "status": "failed",
            "http_status": response.status_code,
            "response": error_data,
        }

    except requests.RequestException as exc:

        return {
            "success": False,
            "status": "error",
            "message": str(exc),
        }