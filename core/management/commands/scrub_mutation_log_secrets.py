from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from core.models import MutationLog
from core.mutation_log_secrets import SECRET_KEY_HINTS, scrub_json_text

BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Mask the passwords and other secrets kept in the mutation log."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count the affected rows without writing anything.",
        )
        parser.add_argument(
            "--include-pending",
            action="store_true",
            help=(
                "Also process the rows left in RECEIVED. Only to be used with "
                "--older-than-hours: a recent row may still be queued, and masking "
                "it would break the mutation."
            ),
        )
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=24,
            help="With --include-pending: minimum age of a RECEIVED row (default 24h).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Pre-selection in the database: no point reading back the rows that cannot
        # hold anything. `icontains` on the serialised text is enough for a rough
        # cut; the real masking then happens in Python on the parsed JSON.
        hint_filter = Q()
        for hint in SECRET_KEY_HINTS:
            hint_filter |= Q(json_content__icontains=hint)
            hint_filter |= Q(client_mutation_details__icontains=hint)

        queryset = MutationLog.objects.filter(hint_filter)

        terminal = Q(status__in=(MutationLog.SUCCESS, MutationLog.ERROR))
        if options["include_pending"]:
            cutoff = timezone.now() - timedelta(hours=options["older_than_hours"])
            queryset = queryset.filter(
                terminal
                | Q(status=MutationLog.RECEIVED, request_date_time__lt=cutoff)
            )
            self.stdout.write(
                f"RECEIVED rows included when older than {cutoff.isoformat()}."
            )
        else:
            queryset = queryset.filter(terminal)

        candidates = queryset.count()
        self.stdout.write(f"{candidates} row(s) to examine.")

        scrubbed = 0
        # `iterator` so as not to load the whole table; the filter above has
        # already ruled out most of it.
        for log in queryset.only(
            "id", "json_content", "client_mutation_details"
        ).iterator(chunk_size=BATCH_SIZE):
            fields = {}
            for name in ("json_content", "client_mutation_details"):
                cleaned = scrub_json_text(getattr(log, name, None))
                if cleaned is not None:
                    fields[name] = cleaned
            if not fields:
                continue
            scrubbed += 1
            if not dry_run:
                MutationLog.objects.filter(id=log.id).update(**fields)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"--dry-run: {scrubbed} row(s) hold a secret, nothing was written."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"{scrubbed} row(s) masked.")
            )
