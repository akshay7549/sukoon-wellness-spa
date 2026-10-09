import re

from django.conf import settings
from django.templatetags.static import static


def add_service_covers(services):
    """Prefer uploaded treatment photos, then matching bundled images."""
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    files = sorted((settings.BASE_DIR / "static" / "images").glob("*"), key=lambda path: path.suffix == ".webp")
    images = {normalize(path.stem): path.name for path in files if path.is_file()}
    for service in services:
        service.cover_url = service.image.url if service.image else static(
            "images/" + images.get(normalize(service.name), "service.webp")
        )
    return services
