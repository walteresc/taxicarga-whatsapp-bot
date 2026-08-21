# Generated migration for unique active conversation constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0017_add_conversation_read_state'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='conversacionwhatsapp',
            constraint=models.UniqueConstraint(
                fields=['cliente', 'channel'],
                condition=models.Q(('cerrada_en__isnull', True)),
                name='unique_active_whatsapp_conversation'
            ),
        ),
    ]
