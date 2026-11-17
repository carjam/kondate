"""Create the first admin account from env vars, if it doesn't exist yet.

Render's free tier has no shell, so the start command runs this on every boot.
It never changes an existing user's password.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL if missing."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            self.stdout.write("ensure_superuser: env vars not set, skipping.")
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"ensure_superuser: {username!r} already exists.")
            return
        User.objects.create_superuser(
            username=username, email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""), password=password
        )
        self.stdout.write(self.style.SUCCESS(f"ensure_superuser: created {username!r}."))
