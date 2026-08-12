from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies=[("integrations","0005_workerheartbeat")]
    operations=[migrations.AddField(
        model_name="channelintegrationpolicy",name="ai_v31_mode",
        field=models.CharField(choices=[("off","Off"),("shadow","Shadow"),("active","Active")],
                               default="off",max_length=12),
    )]
