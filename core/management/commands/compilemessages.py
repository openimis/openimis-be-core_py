import glob
import json
import os
from importlib import resources

from django.core.management import CommandError
from django.core.management.commands import compilemessages
from django.core.management.utils import is_ignored_path, find_command


class Command(compilemessages.Command):
    def handle(self, **options):
        locale = options['locale']
        exclude = options['exclude']
        ignore_patterns = set(options['ignore_patterns'])
        self.verbosity = options['verbosity']
        if options['fuzzy']:
            self.program_options = self.program_options + ['-f']

        if find_command(self.program) is None:
            raise CommandError("Can't find %s. Make sure you have GNU gettext "
                               "tools 0.15 or newer installed." % self.program)

        basedirs = [os.path.join('conf', 'locale'), 'locale']
        if os.environ.get('DJANGO_SETTINGS_MODULE'):
            from django.conf import settings
            basedirs.extend(settings.LOCALE_PATHS)

        # Walk entire tree, looking for locale directories
        apps = []
        for mod in load_openimis_conf()["modules"]:
            mod_name = mod["name"]
            with resources.path(mod_name, "__init__.py") as path:
                apps.append(path.parent.parent)  # This might need to be more restrictive

        for topdir in ["."] + apps:
            for dirpath, dirnames, filenames in os.walk(topdir, topdown=True):
                for dirname in dirnames:
                    if is_ignored_path(os.path.normpath(os.path.join(dirpath, dirname)), ignore_patterns):
                        dirnames.remove(dirname)
                    elif dirname == 'locale':
                        basedirs.append(os.path.join(dirpath, dirname))

        # Gather existing directories.
        basedirs = set(map(os.path.abspath, filter(os.path.isdir, basedirs)))

        if not basedirs:
            raise CommandError("This script should be run from the Django Git "
                               "checkout or your project or app tree, or with "
                               "the settings module specified.")

        # Build locale list
        all_locales = []
        for basedir in basedirs:
            locale_dirs = filter(os.path.isdir, glob.glob('%s/*' % basedir))
            all_locales.extend(map(os.path.basename, locale_dirs))

        # Account for excluded locales
        locales = locale or all_locales
        locales = set(locales).difference(exclude)

        self.has_errors = False
        for basedir in basedirs:
            if locales:
                dirs = [os.path.join(basedir, l, 'LC_MESSAGES') for l in locales]
            else:
                dirs = [basedir]
            locations = []
            for ldir in dirs:
                for dirpath, dirnames, filenames in os.walk(ldir):
                    locations.extend((dirpath, f) for f in filenames if f.endswith('.po'))
            if locations:
                self.compile_messages(locations)

        if self.has_errors:
            raise CommandError('compilemessages generated one or more errors.')


def load_openimis_conf():
    conf_file_path = "../openimis.json"
    with open(conf_file_path) as conf_file:
        return json.load(conf_file)
