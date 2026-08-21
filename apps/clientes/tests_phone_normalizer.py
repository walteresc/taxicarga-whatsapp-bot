"""
Tests for phone number normalization (E.164 format).
"""

from django.test import TestCase
from apps.clientes.phone_normalizer import (
    normalize_phone,
    get_phone_e164,
    phones_are_equivalent,
)


class PhoneNormalizerPeruTest(TestCase):
    """Test Peru phone normalization."""

    def test_peru_9_digits_no_prefix(self):
        """Test 9-digit Peru number without prefix."""
        result = normalize_phone("995403320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")
        self.assertEqual(result["national_number"], "995403320")
        self.assertIsNone(result["error"])

    def test_peru_11_digits_with_51(self):
        """Test 11-digit Peru number with 51 prefix."""
        result = normalize_phone("51995403320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")
        self.assertEqual(result["national_number"], "995403320")

    def test_peru_12_chars_with_plus_51(self):
        """Test 12-char Peru number with +51 prefix."""
        result = normalize_phone("+51995403320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")
        self.assertEqual(result["national_number"], "995403320")

    def test_peru_with_spaces(self):
        """Test Peru number with spaces."""
        result = normalize_phone("51 995 403 320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")

    def test_peru_with_dashes(self):
        """Test Peru number with dashes."""
        result = normalize_phone("51-995-403-320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")

    def test_peru_with_parentheses(self):
        """Test Peru number with parentheses."""
        result = normalize_phone("(51) 995-403-320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")

    def test_peru_plus_with_spaces(self):
        """Test Peru number with + and spaces."""
        result = normalize_phone("+51 995 403 320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")

    def test_peru_invalid_too_short(self):
        """Test Peru number that's too short."""
        result = normalize_phone("99540332", country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_invalid_too_long(self):
        """Test Peru number that's too long."""
        result = normalize_phone("9954033201", country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_invalid_non_digits(self):
        """Test Peru number with non-digit characters."""
        result = normalize_phone("995403xyz", country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_empty_string(self):
        """Test empty phone number."""
        result = normalize_phone("", country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_none(self):
        """Test None phone number."""
        result = normalize_phone(None, country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_only_separators(self):
        """Test phone with only separators."""
        result = normalize_phone("--- --- ---", country_code="PE")
        self.assertFalse(result["is_valid"])
        self.assertIsNotNone(result["error"])

    def test_peru_landline_valid(self):
        """Test Peru landline (starts with 1-8)."""
        result = normalize_phone("12345678", country_code="PE")
        # Landlines are technically valid but less common in WhatsApp
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51" + "12345678")

    def test_peru_mobile_starts_with_9(self):
        """Test Peru mobile (starts with 9)."""
        result = normalize_phone("987654321", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51987654321")


class PhoneNormalizerHelperTest(TestCase):
    """Test helper functions."""

    def test_get_phone_e164_valid(self):
        """Test quick E.164 getter with valid phone."""
        e164 = get_phone_e164("995403320")
        self.assertEqual(e164, "+51995403320")

    def test_get_phone_e164_invalid(self):
        """Test quick E.164 getter with invalid phone."""
        e164 = get_phone_e164("invalid")
        self.assertIsNone(e164)

    def test_phones_are_equivalent_same_variants(self):
        """Test equivalence check on different formats."""
        result = phones_are_equivalent("995403320", "51995403320")
        self.assertTrue(result)

    def test_phones_are_equivalent_with_plus(self):
        """Test equivalence check with + prefix."""
        result = phones_are_equivalent("+51995403320", "51995403320")
        self.assertTrue(result)

    def test_phones_are_equivalent_with_spaces(self):
        """Test equivalence check with spaces."""
        result = phones_are_equivalent("51 995 403 320", "995403320")
        self.assertTrue(result)

    def test_phones_are_equivalent_different(self):
        """Test non-equivalence check."""
        result = phones_are_equivalent("995403320", "987654321")
        self.assertFalse(result)

    def test_phones_are_equivalent_invalid(self):
        """Test equivalence check with invalid numbers."""
        result = phones_are_equivalent("invalid", "987654321")
        self.assertFalse(result)

    def test_phones_are_equivalent_both_invalid(self):
        """Test equivalence check with both invalid."""
        result = phones_are_equivalent("invalid1", "invalid2")
        self.assertFalse(result)

    def test_phones_are_equivalent_none(self):
        """Test equivalence check with None."""
        result = phones_are_equivalent(None, "995403320")
        self.assertFalse(result)


class PhoneNormalizerEdgeCasesTest(TestCase):
    """Test edge cases."""

    def test_whitespace_preservation(self):
        """Test that raw phone is preserved in output."""
        result = normalize_phone("  +51 995 403 320  ", country_code="PE")
        self.assertEqual(result["raw"], "  +51 995 403 320  ")
        self.assertTrue(result["is_valid"])

    def test_multiple_separators(self):
        """Test phone with multiple consecutive separators."""
        result = normalize_phone("51..995--403--320", country_code="PE")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["normalized_e164"], "+51995403320")

    def test_unsupported_country_code(self):
        """Test unsupported country code."""
        result = normalize_phone("1234567890", country_code="US")
        self.assertFalse(result["is_valid"])
        self.assertIn("Unsupported", result["error"])

    def test_default_country_is_peru(self):
        """Test that default country is Peru."""
        result = normalize_phone("995403320")
        self.assertEqual(result["country_code"], "PE")
        self.assertTrue(result["is_valid"])

    def test_result_keys(self):
        """Test that result has all expected keys."""
        result = normalize_phone("995403320")
        expected_keys = {
            "raw", "normalized_e164", "country_code", "national_number",
            "is_valid", "error"
        }
        self.assertEqual(set(result.keys()), expected_keys)
