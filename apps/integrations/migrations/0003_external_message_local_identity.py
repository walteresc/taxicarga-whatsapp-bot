from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integrations", "0002_final_audit_scopes")]

    operations = [
        migrations.AddConstraint(
            model_name="externalmessagemapping",
            constraint=models.UniqueConstraint(
                fields=("provider", "account_scope", "whatsapp_message"),
                condition=models.Q(whatsapp_message__isnull=False),
                name="int_msg_local_provider_uniq",
            ),
        ),
    ]
