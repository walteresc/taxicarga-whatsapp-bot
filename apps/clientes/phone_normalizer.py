"""
Phone normalization utility for E.164 format.

Central function for normalizing phone numbers across the application.
Used by webhook, API, search, imports, and database operations.

For Peru:
- 995403320 → +51995403320
- 51995403320 → +51995403320
- +51995403320 → +51995403320 (unchanged)
- 51 995 403 320 → +51995403320
- +51 995 403 320 → +51995403320
"""

import re
from typing import Optional, Dict, Any


def normalize_phone(phone: Optional[str], country_code: str = "PE") -> Dict[str, Any]:
    """
    Normalize a phone number to E.164 format.

    Args:
        phone: Raw phone number (may include spaces, dashes, parentheses)
        country_code: ISO 3166-1 alpha-2 country code (default: "PE" for Peru)

    Returns:
        {
            "raw": original input,
            "normalized_e164": "+51995403320" or None,
            "country_code": "PE",
            "national_number": "995403320" or None,
            "is_valid": bool,
            "error": error message if invalid,
        }
    """

    result = {
        "raw": phone,
        "normalized_e164": None,
        "country_code": country_code,
        "national_number": None,
        "is_valid": False,
        "error": None,
    }

    # Handle null/empty
    if not phone:
        result["error"] = "Phone number is empty"
        return result

    # Clean input
    phone = str(phone).strip()
    if not phone:
        result["error"] = "Phone number is empty"
        return result

    # Remove common separators
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone)

    if not cleaned:
        result["error"] = "Phone number contains only separators"
        return result

    # Peru-specific logic
    if country_code == "PE":
        return _normalize_peru(cleaned, result)

    # Generic E.164 fallback
    result["error"] = f"Unsupported country code: {country_code}"
    return result


def _normalize_peru(cleaned: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize Peru phone numbers."""

    # Peru country code is +51
    # National number is 9 digits (mobile starts with 9, landline starts with 1-8)
    # Valid formats:
    # - 995403320 (9 digits, no prefix)
    # - 51995403320 (11 digits, with country code)
    # - +51995403320 (12 chars, with + and country code)

    # Remove + if present
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Remove leading 51 (Peru country code) if present
    if cleaned.startswith("51"):
        # Check if it's 51 + 9 digits
        if len(cleaned) == 11:  # 51 + 9 digits
            national = cleaned[2:]
        else:
            result["error"] = f"Invalid Peru phone: {result['raw']} (got {len(cleaned)} digits, expected 11)"
            return result
    else:
        # Should be just 9 digits
        if len(cleaned) == 9:
            national = cleaned
        else:
            result["error"] = f"Invalid Peru phone: {result['raw']} (got {len(cleaned)} digits, expected 9 or 11)"
            return result

    # Validate national number
    if not national.isdigit():
        result["error"] = f"Phone contains non-digits: {national}"
        return result

    if len(national) != 9:
        result["error"] = f"Peru phone must have 9 digits, got {len(national)}"
        return result

    # Mobile must start with 9
    if not national.startswith("9"):
        # Landline starts with 1-8, less common in WhatsApp context but valid
        pass

    # Success
    result["normalized_e164"] = f"+51{national}"
    result["national_number"] = national
    result["is_valid"] = True
    result["error"] = None

    return result


def get_phone_e164(phone: Optional[str]) -> Optional[str]:
    """
    Quick normalization: return E.164 format or None if invalid.

    Useful for inline usage.
    """
    result = normalize_phone(phone)
    return result["normalized_e164"] if result["is_valid"] else None


def phones_are_equivalent(phone1: Optional[str], phone2: Optional[str]) -> bool:
    """
    Check if two phone numbers normalize to the same value.

    Useful for deduplication and comparison.
    """
    if not phone1 or not phone2:
        return False

    norm1 = normalize_phone(phone1)
    norm2 = normalize_phone(phone2)

    if not norm1["is_valid"] or not norm2["is_valid"]:
        return False

    return norm1["normalized_e164"] == norm2["normalized_e164"]
