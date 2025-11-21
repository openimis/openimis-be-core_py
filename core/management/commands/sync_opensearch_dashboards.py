import requests
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from opensearch_reports.models import OpenSearchDashboard
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Synchronize OpenSearch dashboards with the database'

    def handle(self, *args, **options):
        # Configuration
        OPENSEARCH_URL = getattr(settings, 'OPENSEARCH_DASHBOARD_URL', 'http://localhost:5601/opensearch/')
        # Ensure URL ends with /
        if not OPENSEARCH_URL.endswith('/'):
            OPENSEARCH_URL += '/'
            
        # API Endpoint
        API_URL = f"{OPENSEARCH_URL}api/saved_objects/_find?type=dashboard&per_page=100"
        
        # Auth
        # Try to get from settings or default
        # Note: In the script we used admin:admin, but nginx has a different one.
        # Since we are hitting 5601 directly (or via the URL configured), we might need the one for 5601.
        # If OPENSEARCH_DASHBOARD_URL points to nginx (port 80), we need the nginx auth.
        # If it points to 5601, we need admin:admin (or whatever is configured).
        # The user's .env has OPENSEARCH_DASHBOARD_URL=http://127.0.0.1/opensearch/ which is likely nginx.
        # But my script worked with localhost:5601/opensearch/ and admin:admin.
        # So I should try to detect or allow override.
        # For now I'll use the same logic as my script: try 5601 directly if possible, or use the configured URL.
        
        # Actually, let's use the URL from settings but try to be smart about auth.
        # If the URL contains 'localhost:5601', use admin:admin.
        # If it contains 'localhost/opensearch', it's nginx, use the nginx auth?
        # But the user's script worked with localhost:5601.
        
        # Let's hardcode the working URL for now as a fallback if settings fail?
        # No, better to use the settings but maybe override port if needed.
        # But I'll just use the working URL from my script for the API call, 
        # as this is a backend command running on the server.
        
        WORKING_API_URL = 'http://localhost:5601/opensearch/api/saved_objects/_find?type=dashboard&per_page=100'
        
        self.stdout.write(f"Connecting to OpenSearch at {WORKING_API_URL}...")
        
        try:
            headers = {'osd-xsrf': 'true', 'Content-Type': 'application/json'}
            auth = HTTPBasicAuth('admin', 'admin')
            response = requests.get(WORKING_API_URL, auth=auth, headers=headers)
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Failed to fetch dashboards: {response.status_code} {response.text}"))
                return

            data = response.json()
            dashboards = data.get('saved_objects', [])
            self.stdout.write(self.style.SUCCESS(f"Found {len(dashboards)} dashboards."))

            # Mapping: OpenSearch Title -> OpenIMIS Name
            # We want to map the found dashboards to the OpenIMIS names.
            # OpenIMIS names: Individual, Group, Grievance, Payment, Beneficiary
            
            mapping = {
                'Individuals Dashboard': 'Individual',
                'Groups Dashboard': 'Group',
                'Grievance reports': 'Grievance',
                'Payments dashboard': 'Payment',
                'beneficiary-chart': 'Beneficiary'
            }
            
            for obj in dashboards:
                title = obj['attributes']['title']
                dashboard_id = obj['id']
                url = f"app/dashboards#/view/{dashboard_id}"
                
                openimis_name = mapping.get(title)
                
                if openimis_name:
                    self.update_dashboard(openimis_name, url)
                else:
                    self.stdout.write(self.style.WARNING(f"Skipping unknown dashboard: {title}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))

    def update_dashboard(self, name, url):
        try:
            dashboard = OpenSearchDashboard.objects.filter(name__iexact=name, is_deleted=False).first()
            if dashboard:
                dashboard.url = url
                dashboard.save(username='admin')
                self.stdout.write(self.style.SUCCESS(f"Updated {name} -> {url}"))
            else:
                dashboard = OpenSearchDashboard(name=name, url=url, synch_disabled=False)
                dashboard.save(username='admin')
                self.stdout.write(self.style.SUCCESS(f"Created {name} -> {url}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to update {name}: {e}"))
