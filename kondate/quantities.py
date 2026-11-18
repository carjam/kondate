"""Best-effort merging of free-text recipe amounts for the shopping list.

Amounts are typed by hand ("1/2 cup", "2 medium", "to taste"), so this never
converts units or guesses. It only adds amounts that start with a number and
share the same unit word(s); everything else is listed as written:

    combine_amounts(["1", "2"])                    -> "3"
    combine_amounts(["1/2 cup", "1 1/2 cups"])     -> "2 cups"
    combine_amounts(["2 tsp", "1 tbsp", "pinch"])  -> "2 tsp + 1 tbsp + pinch"
"""

from __future__ import annotations

import re
from fractions import Fraction

_UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4", "⅛": "1/8"}

# A leading quantity: "1 1/2", "1/2", "2", "2.5". The unit is whatever follows,
# unless it looks like a range ("8 to 12", "2-3"), which we leave untouched.
_QUANTITY = re.compile(r"^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)(?:\s+|$)(.*)$")
_RANGE = re.compile(r"^(?:to|or|-|–)\b|^[-–]")


def parse_amount(text: str) -> tuple[Fraction, str] | None:
    """Split "1 1/2 cups" into (Fraction(3, 2), "cups"); None if not numeric."""
    for glyph, ascii_fraction in _UNICODE_FRACTIONS.items():
        text = text.replace(glyph, f" {ascii_fraction}")
    text = " ".join(text.split())
    match = _QUANTITY.match(text)
    if not match:
        return None
    number, unit = match.groups()
    if _RANGE.match(unit):
        return None
    try:
        if " " in number:
            whole, frac = number.split()
            quantity = int(whole) + Fraction(frac)
        else:
            quantity = Fraction(number)
    except (ValueError, ZeroDivisionError):
        return None
    return quantity, unit


def _unit_key(unit: str) -> str:
    key = unit.lower().rstrip(".")
    # Crude singular/plural folding: "cups" ~ "cup", "cloves" ~ "clove".
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key


def format_quantity(quantity: Fraction) -> str:
    if quantity.denominator == 1:
        return str(quantity.numerator)
    if quantity.denominator > 16:
        return f"{float(quantity):.2f}".rstrip("0").rstrip(".")
    whole, rest = divmod(quantity.numerator, quantity.denominator)
    fraction = f"{rest}/{quantity.denominator}"
    return f"{whole} {fraction}" if whole else fraction


def combine_amounts(amounts: list[str]) -> str:
    totals: dict[str, Fraction] = {}
    spellings: dict[str, list[str]] = {}
    unparsed: list[str] = []
    for raw in amounts:
        raw = raw.strip()
        if not raw:
            continue
        parsed = parse_amount(raw)
        if parsed is None:
            unparsed.append(raw)
            continue
        quantity, unit = parsed
        key = _unit_key(unit)
        totals[key] = totals.get(key, Fraction(0)) + quantity
        spellings.setdefault(key, []).append(unit)

    parts = []
    for key, total in totals.items():
        seen = spellings[key]
        unit = seen[0]
        if total > 1:  # prefer a plural spelling if one was typed
            unit = next((s for s in seen if s.lower().endswith("s")), unit)
        parts.append(f"{format_quantity(total)} {unit}".strip())
    return " + ".join(parts + unparsed)
