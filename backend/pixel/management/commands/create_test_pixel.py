"""
Create or fetch a test PixelInstallation for local E2E testing.

Idempotent: re-running prints the existing record. Picks (or creates) a
superuser as the advertiser and whitelists localhost + 127.0.0.1 so
pixel/test-page/index.html can post events from `python -m http.server`.

Usage:
    python manage.py create_test_pixel
"""

from django.core.management.base import BaseCommand

from core.models import User
from pixel.models import PixelInstallation


TEST_ALLOWED_DOMAINS = ["localhost", "127.0.0.1"]
TEST_USERNAME = "test_advertiser"
TEST_EMAIL = "test_advertiser@aimaa.uz"


class Command(BaseCommand):
    help = "Create / fetch a test PixelInstallation for local E2E testing."

    def handle(self, *args, **options):
        advertiser = self._resolve_advertiser()
        pixel, created = PixelInstallation.objects.get_or_create(
            advertiser=advertiser,
            defaults={
                "allowed_domains": TEST_ALLOWED_DOMAINS,
                "debug_mode": True,
                "enabled": True,
            },
        )

        # Ensure localhost is whitelisted even on a pre-existing record.
        changed = False
        for domain in TEST_ALLOWED_DOMAINS:
            if domain not in (pixel.allowed_domains or []):
                pixel.allowed_domains = list(pixel.allowed_domains or []) + [domain]
                changed = True
        if not pixel.debug_mode:
            pixel.debug_mode = True
            changed = True
        if changed:
            pixel.save(update_fields=["allowed_domains", "debug_mode"])

        pixel_id_str = str(pixel.pixel_id)
        status_label = "created" if created else "fetched (already existed)"

        self.stdout.write(self.style.SUCCESS(f"Pixel {status_label}."))
        self.stdout.write("")
        self.stdout.write(f"  pixel_id        : {pixel_id_str}")
        self.stdout.write(f"  advertiser      : {advertiser.username} ({advertiser.email})")
        self.stdout.write(f"  allowed_domains : {pixel.allowed_domains}")
        self.stdout.write(f"  debug_mode      : {pixel.debug_mode}")
        self.stdout.write(f"  enabled         : {pixel.enabled}")
        self.stdout.write("")
        self.stdout.write("Paste this into pixel/test-page/index.html:")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'  <script src="../dist/pixel.js" data-pixel-id="{pixel_id_str}"></script>'
        ))
        self.stdout.write("")
        self.stdout.write("Then serve the page:")
        self.stdout.write("  cd pixel/test-page && python -m http.server 8080")

    def _resolve_advertiser(self) -> User:
        # Prefer an existing superuser so the test pixel is owned by a real
        # local admin; fall back to a dedicated test user.
        user = User.objects.filter(is_superuser=True).first()
        if user is not None:
            return user

        user, created = User.objects.get_or_create(
            username=TEST_USERNAME,
            defaults={
                "email": TEST_EMAIL,
                "role": getattr(User.Role, "ADVERTISER", "advertiser"),
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            self.stdout.write(self.style.WARNING(
                f"Created placeholder advertiser '{TEST_USERNAME}' (no password set)."
            ))
        return user
