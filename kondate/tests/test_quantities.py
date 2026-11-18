from fractions import Fraction

import pytest

from kondate.quantities import combine_amounts, format_quantity, parse_amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2", (Fraction(2), "")),
        ("1/2 cup", (Fraction(1, 2), "cup")),
        ("1 1/2 cups", (Fraction(3, 2), "cups")),
        ("2.5 lb", (Fraction(5, 2), "lb")),
        ("½ tsp", (Fraction(1, 2), "tsp")),
        ("1 orange", (Fraction(1), "orange")),  # "or" inside a word isn't a range
        ("to taste", None),
        ("8 to 12", None),
        ("2-3 cloves", None),
        ("2 - 3", None),
        ("1 or 2", None),
        ("", None),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        (["1", "2"], "3"),
        (["1/2 cup", "1 1/2 cups"], "2 cups"),
        (["1/4 cup", "1/4 cup"], "1/2 cup"),
        (["2 cloves", "1 clove"], "3 cloves"),
        (["1 Cup", "1 cup"], "2 Cup"),  # case-insensitive match keeps the first spelling
        (["2 tsp", "1 tbsp"], "2 tsp + 1 tbsp"),  # never converts units
        (["1 medium", "1 large"], "1 medium + 1 large"),
        (["1 cup", "to taste", "", "  "], "1 cup + to taste"),
        (["8 to 12", "4"], "4 + 8 to 12"),
        ([], ""),
    ],
)
def test_combine_amounts(amounts, expected):
    assert combine_amounts(amounts) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Fraction(3), "3"), (Fraction(3, 2), "1 1/2"), (Fraction(1, 3), "1/3"), (Fraction(1, 30), "0.03")],
)
def test_format_quantity(value, expected):
    assert format_quantity(value) == expected
