from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="BotConversationState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("conversation_key", models.CharField(max_length=160, unique=True)),
                ("service_type", models.CharField(default="mudanza", max_length=40)),
                ("state_data", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("collecting", "Recolectando datos"), ("ready_for_quote", "Lista para cotizar")], default="collecting", max_length=24)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["conversation_key"]},
        ),
    ]
