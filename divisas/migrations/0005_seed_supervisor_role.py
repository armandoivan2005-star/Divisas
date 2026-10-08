from django.db import migrations


def create_supervisor_role(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    group_model.objects.get_or_create(name='SUPERVISOR')


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0004_seed_user_roles'),
    ]

    operations = [
        migrations.RunPython(create_supervisor_role, migrations.RunPython.noop),
    ]
