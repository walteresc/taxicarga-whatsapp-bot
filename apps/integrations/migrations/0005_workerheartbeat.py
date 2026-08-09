from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("integrations", "0004_channelintegrationpolicy")]
    operations = [
        migrations.CreateModel(
            name="WorkerHeartbeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("worker_id", models.CharField(max_length=120)),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
        ),
    ]
