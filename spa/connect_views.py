import base64
from io import BytesIO

import qrcode
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse


ADDRESS = "Dwarka City Center Mall, 2nd Floor, Majhaulia Road, Gobarsahi, Muzaffarpur, Bihar 842002"
INSTAGRAM_URL = "https://www.instagram.com/sukoonwellnessandspa/"
FACEBOOK_URL = "https://www.facebook.com/profile.php?id=61592578171369"
WHATSAPP_URL = (
    "https://api.whatsapp.com/send/?phone=919031640551"
    "&text=Hello+Sukoon+Wellness+%26+Spa%2C+I+would+like+to+book+an+appointment."
    "&type=phone_number&app_absent=0"
)
MAPS_URL = (
    "https://www.google.com/maps/search/?api=1"
    "&query=Sukoon+Wellness+%26+Spa+Dwarka+City+Center+Mall+Muzaffarpur+Bihar"
)


def connect_url():
    return settings.PUBLIC_SITE_URL.rstrip("/") + reverse("connect")


def connect_qr_data_uri(box_size=8):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=4)
    qr.add_data(connect_url())
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def connect(request):
    return render(request, "spa/connect.html", {
        "instagram_url": INSTAGRAM_URL,
        "facebook_url": FACEBOOK_URL,
        "whatsapp_url": WHATSAPP_URL,
        "maps_url": MAPS_URL,
        "address": ADDRESS,
        "canonical_url": connect_url(),
        "qr_code": connect_qr_data_uri(box_size=16),
    })
