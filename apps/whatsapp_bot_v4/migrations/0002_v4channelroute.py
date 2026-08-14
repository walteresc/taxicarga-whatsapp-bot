from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("whatsapp", "0013_request_lifecycle_observability"),
        ("whatsapp_bot_v4", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="V4ChannelRoute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("channel", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="v4_route", to="whatsapp.whatsappchannel")),
            ],
        ),
    ]
