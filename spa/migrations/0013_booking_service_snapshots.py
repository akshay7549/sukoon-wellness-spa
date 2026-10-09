from django.db import migrations

def fill_snapshots(apps, schema_editor):
    Booking=apps.get_model("spa","Booking")
    for booking in Booking.objects.using(schema_editor.connection.alias).select_related("service").filter(service_name_snapshot="").iterator():
        if booking.service_id:
            Booking.objects.using(schema_editor.connection.alias).filter(pk=booking.pk).update(service_name_snapshot=booking.service.name)

class Migration(migrations.Migration):
    dependencies=[("spa","0012_customerprofile_enquiry_notification_ratelimitbucket_and_more")]
    operations=[migrations.RunPython(fill_snapshots,migrations.RunPython.noop)]
