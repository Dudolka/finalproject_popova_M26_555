"""Tests for currency cross-rate calculations."""

import unittest

from valutatrade_hub.core.utils import cross_rate


class TestCurrencyConversion(unittest.TestCase):
    """Verify cross rates use USD-per-unit quote directions."""

    def test_direct_quote(self):
        self.assertEqual(cross_rate(50000, 1), 50000)

    def test_cross_currency(self):
        self.assertAlmostEqual(cross_rate(50000, 1.25), 40000)

    def test_reject_non_finite_and_zero(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cross_rate(1, value)


if __name__ == "__main__":
    unittest.main()
