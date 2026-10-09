import base64
from html import escape
from io import BytesIO

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from PIL import Image

from .connect_views import ADDRESS, FACEBOOK_URL, INSTAGRAM_URL, WHATSAPP_URL, connect_qr_data_uri, connect_url


class ConnectPageTests(SimpleTestCase):
    def test_public_page_contains_all_requested_destinations(self):
        response = self.client.get(reverse("connect"))
        self.assertEqual(response.status_code, 200)
        for target in (INSTAGRAM_URL, FACEBOOK_URL, WHATSAPP_URL):
            self.assertContains(response, f'href="{escape(target)}"')
        self.assertContains(response, f'href="{reverse("booking")}"')
        self.assertContains(response, f'href="{reverse("home")}"')
        self.assertContains(response, ADDRESS)
        self.assertContains(response, "Get Directions")
        self.assertNotContains(response, "Sign In")
        self.assertContains(response, "Print QR")
        self.assertContains(response, 'src="data:image/png;base64,')
        content = response.content.decode()
        self.assertLess(content.index('class="reception-qr"'), content.index('class="link-list"'))

    def test_qr_destination_uses_public_domain(self):
        self.assertEqual(connect_url(), "https://sukoonwellnessandspa.in/connect/")

    @override_settings(PUBLIC_SITE_URL="https://example.com/")
    def test_public_base_url_handles_trailing_slash(self):
        self.assertEqual(connect_url(), "https://example.com/connect/")

    def test_qr_is_embedded_as_a_square_png_with_a_white_quiet_zone(self):
        uri = connect_qr_data_uri()
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        image = Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")
        self.assertEqual(image.width, image.height)
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(image.getpixel((31, 31)), (255, 255, 255))
        self.assertEqual(image.getpixel((32, 32)), (0, 0, 0))
