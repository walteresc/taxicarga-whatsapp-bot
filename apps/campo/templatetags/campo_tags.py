import builtins

from django import template

register = template.Library()


@register.filter
def getattr(obj, attr):
    return builtins.getattr(obj, attr, "")


@register.filter
def get_item(d, key):
    return d.get(key, {})
