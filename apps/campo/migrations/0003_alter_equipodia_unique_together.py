from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0002_add_fields_to_vehiculo_conductor'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='equipodia',
            unique_together={('fecha', 'vehiculo', 'conductor')},
        ),
    ]
