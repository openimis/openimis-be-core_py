from django.core.management.base import BaseCommand, CommandError

from core.cache_control import (
    UnknownCacheAliasError,
    flush_caches,
    list_cache_info,
    resolve_cache_aliases,
)


class Command(BaseCommand):
    help = (
        "Flush Django caches. With no aliases, every cache in settings.CACHES "
        "is cleared. Pass one or more aliases to flush only those caches."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "aliases",
            nargs="*",
            help="Cache aliases to flush. If omitted, all caches are flushed.",
        )
        parser.add_argument(
            "--alias",
            action="append",
            dest="alias_flags",
            default=[],
            help="Cache alias to flush (repeatable). Same as positional aliases.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_caches",
            help="List configured cache aliases and exit.",
        )

    def handle(self, *args, **options):
        aliases = list(options.get("aliases") or [])
        aliases.extend(options.get("alias_flags") or [])

        if options.get("list_caches"):
            self._list_caches()
            return

        try:
            resolved = resolve_cache_aliases(aliases or None)
        except UnknownCacheAliasError as exc:
            raise CommandError(str(exc)) from exc

        flushed, errors = flush_caches(resolved)
        for alias in flushed:
            self.stdout.write(self.style.SUCCESS("Flushed cache '%s'" % alias))
        for alias, message in errors:
            self.stderr.write(
                self.style.ERROR("Failed to flush cache '%s': %s" % (alias, message))
            )
        if errors:
            raise CommandError(
                "Failed to flush %d cache(s)" % len(errors)
            )
        if len(flushed) == 1:
            self.stdout.write(self.style.SUCCESS("Flushed 1 cache."))
        else:
            self.stdout.write(
                self.style.SUCCESS("Flushed %d caches." % len(flushed))
            )

    def _list_caches(self):
        rows = list_cache_info()
        if not rows:
            self.stdout.write("No caches configured.")
            return
        self.stdout.write("Configured caches:")
        for info in rows:
            extras = []
            if info["key_prefix"]:
                extras.append("prefix=%s" % info["key_prefix"])
            if info["location"]:
                extras.append("location=%s" % info["location"])
            suffix = " (%s)" % ", ".join(extras) if extras else ""
            self.stdout.write(
                "  - %s [%s]%s" % (info["alias"], info["backend_short"], suffix)
            )
