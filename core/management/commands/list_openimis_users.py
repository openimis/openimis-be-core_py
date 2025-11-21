import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'List OpenIMIS (Django) users and export to CSV'

    def add_arguments(self, parser):
        parser.add_argument('--output', '-o', type=str, help='Output CSV file path (defaults to stdout)')

    def handle(self, *args, **options):
        output = options.get('output')
        User = get_user_model()
        qs = User.objects.all().values('id', 'username', 'email', 'first_name', 'last_name')

        fieldnames = ['id', 'username', 'email', 'first_name', 'last_name']

        if output:
            f = open(output, 'w', newline='', encoding='utf-8')
        else:
            import sys
            f = sys.stdout

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in qs:
            writer.writerow(row)

        if output:
            f.close()
            self.stdout.write(self.style.SUCCESS(f'Wrote {qs.count()} users to {output}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Wrote {qs.count()} users to stdout'))
