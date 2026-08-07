from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('campo', '0004_equipo_conductores_ayudantes'),
    ]

    operations = [
        migrations.CreateModel(
            name='EquipoFrecuente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120, verbose_name='Nombre / Alias')),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('vehiculo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='equipos_frecuentes', to='campo.vehiculo')),
                ('conductor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='equipos_frecuentes', to='campo.conductor')),
                ('ayudantes', models.ManyToManyField(blank=True, related_name='equipos_frecuentes', to='campo.ayudante')),
                ('conductores_ayudantes', models.ManyToManyField(blank=True, related_name='equipos_frecuentes_como_ayudante', to='campo.conductor')),
            ],
            options={
                'verbose_name': 'Equipo frecuente',
                'verbose_name_plural': 'Equipos frecuentes',
                'ordering': ['orden', 'nombre'],
            },
        ),
    ]
