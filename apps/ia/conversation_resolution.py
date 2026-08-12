from dataclasses import dataclass

from apps.whatsapp.models import MensajeWhatsApp

from .models import AIDeltaAudit


@dataclass(frozen=True)
class LastQuestionResolution:
    status:str
    targets:tuple
    unresolved_attempts:int=0


def last_question_resolution(conversation):
    bot=MensajeWhatsApp.objects.filter(conversacion=conversation,
        origen=MensajeWhatsApp.ORIGEN_BOT).exclude(question_targets=[]).order_by("-id").first()
    if not bot:return LastQuestionResolution("NONE",())
    inbound=MensajeWhatsApp.objects.filter(conversacion=conversation,
        origen=MensajeWhatsApp.ORIGEN_CLIENTE,id__gt=bot.id).order_by("id").first()
    if not inbound:
        prior_bots=MensajeWhatsApp.objects.filter(conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_BOT,id__lt=bot.id).exclude(question_targets=[]).order_by("-id")
        for prior_bot in prior_bots[:3]:
            prior_inbound=MensajeWhatsApp.objects.filter(conversacion=conversation,
                origen=MensajeWhatsApp.ORIGEN_CLIENTE,id__gt=prior_bot.id,id__lt=bot.id).order_by("id").first()
            if prior_inbound:
                prior_audit=AIDeltaAudit.objects.filter(message_id=prior_inbound.id).first()
                if not prior_audit:return LastQuestionResolution("UNRESOLVED",tuple(prior_bot.question_targets),1)
                prior_delta=prior_audit.accepted_delta or {}
                prior_resolved=_resolved_keys(prior_delta)
                prior_expected={_key(item) for item in prior_bot.question_targets}
                prior_matched=prior_expected & prior_resolved
                if not(prior_expected and prior_matched==prior_expected):
                    return LastQuestionResolution("UNRESOLVED",tuple(prior_bot.question_targets),_attempt_count(conversation,prior_bot))
        return LastQuestionResolution("WAITING",tuple(bot.question_targets))
    audit=AIDeltaAudit.objects.filter(message_id=inbound.id).first()
    if not audit:return LastQuestionResolution("UNRESOLVED",tuple(bot.question_targets),1)
    delta=audit.accepted_delta or {}
    ambiguities=delta.get("ambiguities",[]) or (audit.raw_delta or {}).get("ambiguities",[])
    if ambiguities:return LastQuestionResolution("AMBIGUOUS",tuple(bot.question_targets),1)
    resolved=_resolved_keys(delta)
    expected={_key(item) for item in bot.question_targets}
    matched=expected & resolved
    if expected and matched==expected:return LastQuestionResolution("RESOLVED",tuple(bot.question_targets),0)
    if matched:return LastQuestionResolution("PARTIAL",tuple(bot.question_targets),1)
    return LastQuestionResolution("UNRESOLVED",tuple(bot.question_targets),_attempt_count(conversation,bot))


def _resolved_keys(delta):
    changes=delta.get("changes",{})
    keys={(field,None) for field,value in changes.get("lead",{}).items() if value is not None}
    for location in changes.get("locations",[]):
        for field,value in location.get("set",{}).items():
            if value is not None:keys.add((field,location.get("ref")))
    return keys


def _key(target):return target.get("field"),target.get("ref")


def _attempt_count(conversation,bot):
    key=tuple(_key(item) for item in bot.question_targets)
    count=0
    for row in MensajeWhatsApp.objects.filter(conversacion=conversation,
            origen=MensajeWhatsApp.ORIGEN_BOT).exclude(question_targets=[]).order_by("-id")[:5]:
        if tuple(_key(item) for item in row.question_targets)!=key:break
        count+=1
    return count
