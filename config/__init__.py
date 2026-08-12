# Patch DRF's format_suffix_patterns to handle duplicate converter registration
# This happens when manage.py is invoked multiple times (tests, worker, commands)
import rest_framework.urlpatterns
_original_format_suffix = rest_framework.urlpatterns.format_suffix_patterns
def _patched_format_suffix(urlpatterns, suffix_pattern=None, allowed=None):
    try:
        return _original_format_suffix(urlpatterns, suffix_pattern, allowed)
    except ValueError as e:
        if "already registered" in str(e):
            # Converter already registered, just return the patterns as-is
            return urlpatterns
        raise
rest_framework.urlpatterns.format_suffix_patterns = _patched_format_suffix
