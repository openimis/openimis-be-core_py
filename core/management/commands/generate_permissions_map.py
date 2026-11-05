import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from core.utils import build_permissions_map


class Command(BaseCommand):
    help = "Generate permissions_map.json from collected GQL permissions and sync Django Permission model"

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='./permissions_map.json',
            help='Output file path for the permissions map JSON'
        )
        parser.add_argument(
            '--sync-permissions',
            action='store_true',
            help='Sync Django Permission model with GQL permissions'
        )

    def handle(self, *args, **options):
        output_path = options['output']
        sync_perms = options['sync_permissions']

        self.stdout.write(f"Generating permissions map to {output_path}")

        sorted_map = build_permissions_map()

        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write to JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(sorted_map, f, indent=4, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f"Permissions map generated successfully at {output_path}"))

        if sync_perms:
            self._sync_permissions(sorted_map)

    def _sync_permissions(self, permissions_map):
        """
        Sync Django Permission model with the permissions map.
        """
        # Get or create a dummy content type for GQL permissions
        ct, created = ContentType.objects.get_or_create(
            app_label='core',
            model='gqlpermission',
            defaults={'name': 'GQL Permission'}
        )

        existing_perms = set(Permission.objects.filter(content_type=ct).values_list('codename', flat=True))
        map_codes = set(str(code) for code in permissions_map.values())

        # Create missing permissions
        to_create = map_codes - existing_perms
        for code in to_create:
            # Find the key for this code
            key = next((k for k, v in permissions_map.items() if str(v) == code), f"unknown_{code}")
            name = key.replace('_', ' ').replace('.', ' ').title()
            Permission.objects.create(
                name=name,
                codename=code,
                content_type=ct
            )
            self.stdout.write(f"Created permission: {code} - {name}")

        # Remove extra permissions (optional, commented out for safety)
        # to_remove = existing_perms - map_codes
        # Permission.objects.filter(content_type=ct, codename__in=to_remove).delete()
        # for code in to_remove:
        #     self.stdout.write(f"Removed permission: {code}")

        self.stdout.write(self.style.SUCCESS("Permissions synced with Django Permission model"))
