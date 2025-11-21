"""
Management command to create OpenSearch dashboard entries in the database.
These dashboard records are used by the frontend to redirect to specific OpenSearch dashboards.

Usage:
    python manage.py create_opensearch_dashboard --name "Individual" --url "app/home"
"""

from django.core.management.base import BaseCommand
from opensearch_reports.models import OpenSearchDashboard
from core.models import User


class Command(BaseCommand):
    help = 'Creates an OpenSearch dashboard entry in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            required=True,
            help='Dashboard name (e.g., "Individual", "Group", "Beneficiary", etc.)'
        )
        parser.add_argument(
            '--url',
            type=str,
            required=True,
            help='Dashboard URL path (e.g., "app/dashboards#/view/dashboard-id" or "app/home")'
        )
        parser.add_argument(
            '--synch-disabled',
            action='store_true',
            help='Set synchronization disabled flag'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing dashboard if it exists'
        )

    def handle(self, *args, **options):
        name = options['name']
        url = options['url']
        synch_disabled = options.get('synch_disabled', False)
        update = options.get('update', False)

        # Check if dashboard already exists
        existing = OpenSearchDashboard.objects.filter(name__iexact=name, is_deleted=False).first()
        
        if existing and not update:
            self.stdout.write(
                self.style.WARNING(
                    f'Dashboard "{name}" already exists with URL: {existing.url}\n'
                    f'Use --update flag to update it.'
                )
            )
            return

        if existing and update:
            # Update existing dashboard
            existing.url = url
            existing.synch_disabled = synch_disabled
            existing.save(username='admin')
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Updated dashboard "{name}":\n'
                    f'  - URL: {url}\n'
                    f'  - Synch Disabled: {synch_disabled}\n'
                    f'  - ID: {existing.id}'
                )
            )
        else:
            # Create new dashboard
            dashboard = OpenSearchDashboard(
                name=name,
                url=url,
                synch_disabled=synch_disabled
            )
            dashboard.save(username='admin')
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Created dashboard "{name}":\n'
                    f'  - URL: {url}\n'
                    f'  - Synch Disabled: {synch_disabled}\n'
                    f'  - ID: {dashboard.id}'
                )
            )

        # Show usage info
        self.stdout.write(
            self.style.HTTP_INFO(
                f'\nThis dashboard will be accessible at:\n'
                f'  http://localhost:3000/front/{name.lower()}Reports\n'
                f'\nThe frontend will load the OpenSearch dashboard from:\n'
                f'  http://localhost/opensearch/{url}'
            )
        )
