from django.core.management.base import BaseCommand,CommandError

from apps.integrations.models import ChannelIntegrationPolicy
from apps.whatsapp.models import WhatsAppChannel


class Command(BaseCommand):
    help="Set V3.1 policy for one channel. Active is restricted to TEST channels."

    def add_arguments(self,parser):
        parser.add_argument("channel_id",type=int)
        parser.add_argument("mode",choices=["off","shadow","active"])

    def handle(self,*args,**options):
        channel=WhatsAppChannel.objects.get(pk=options["channel_id"])
        mode=options["mode"]
        if mode == "active" and "test" not in channel.nombre.casefold():
            raise CommandError("V3.1 active is restricted to a TEST channel.")
        policy,_=ChannelIntegrationPolicy.objects.get_or_create(channel=channel)
        policy.enabled=True
        policy.ai_v31_mode=mode
        policy.save(update_fields=["enabled","ai_v31_mode","updated_at"])
        self.stdout.write(self.style.SUCCESS(
            f"AI_V31 channel={channel.id} mode={mode}"))
