from django.db import migrations


def migrate_legacy_ca_eo_profiles(apps, schema_editor):
    from core.services.userBusinessAccessServices import (
        migrate_claim_admins_to_business_access,
        migrate_officers_to_business_access,
    )

    migrate_claim_admins_to_business_access()
    migrate_officers_to_business_access()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_historicaluserbusinessaccess_link_type_and_more"),
        ("location", "0019_alter_location_code"),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_ca_eo_profiles,
            migrations.RunPython.noop,
        ),
    ]