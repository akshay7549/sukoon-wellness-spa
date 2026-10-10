from django.db import migrations


def franchise_stages(apps, schema_editor):
    Enquiry = apps.get_model('spa', 'Enquiry')
    Task = apps.get_model('spa', 'FollowUpTask')
    mapping = {'contacted': 'qualification', 'interested': 'proposal', 'booked': 'meeting', 'converted': 'closed', 'lost': 'closed'}
    for lead in Enquiry.objects.using(schema_editor.connection.alias).filter(kind='franchise', status__in=mapping):
        old = lead.status
        lead.status = mapping[old]
        lead.staff_notes = (lead.staff_notes + '\nPrevious franchise stage: ' + old).strip()
        if lead.status == 'closed':
            Task.objects.using(schema_editor.connection.alias).filter(lead_id=lead.pk, status='pending').update(status='cancelled')
            lead.next_task_id = None
        lead.save(update_fields=['status', 'staff_notes', 'next_task'])


class Migration(migrations.Migration):
    dependencies = [('spa', '0022_reception_franchise_rewards')]
    operations = [migrations.RunPython(franchise_stages, migrations.RunPython.noop)]
