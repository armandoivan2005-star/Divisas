from django.db import migrations


def create_user_roles(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    group_model.objects.get_or_create(name='ADMINISTRADOR')
    group_model.objects.get_or_create(name='NORMAL')


class Migration(migrations.Migration):

    dependencies = [
        ('divisas', '0003_exchangealert_useralertnotification'),
    ]

    operations = [
        migrations.RunPython(create_user_roles, migrations.RunPython.noop),
    ]
