from django.db import migrations
from django.db.migrations.recorder import MigrationRecorder

def preserve_unknown_payments(apps, schema_editor):
    connection = schema_editor.connection
    migration = MigrationRecorder(connection).migration_qs.filter(
        app="spa", name="0012_customerprofile_enquiry_notification_ratelimitbucket_and_more"
    ).first()
    if migration:
        Booking = apps.get_model("spa", "Booking")
        Booking.objects.using(connection.alias).filter(
            updated_at__lte=migration.applied, amount_paid=0,
            payment_mode="", payment_reference=""
        ).update(amount_paid=None)

class Migration(migrations.Migration):
    dependencies = [("spa", "0014_alter_booking_amount_paid")]
    operations = [migrations.RunPython(preserve_unknown_payments, migrations.RunPython.noop)]
