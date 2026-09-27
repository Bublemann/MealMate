"""Barcodes typed in or scanned (BAR-01): EAN-13, EAN-8, UPC-A and UPC-E.

All of them end in a GS1 check digit. A UPC-E code is 8 digits long like an EAN-8; its check
digit belongs to the UPC-A code it abbreviates, so an 8-digit code passes if it is valid either
way.

One product has one stored form (its GTIN-13), so that it cannot be stored twice: a UPC-A code is
the EAN-13 with a leading 0, and a UPC-E code stands for a UPC-A code. EAN-8 codes are their own
GTIN-8 number range and stay 8 digits; an 8-digit code valid both as EAN-8 and as UPC-E counts
as EAN-8.
"""

import re

_DIGITS = re.compile(r"[0-9]+")
EAN_13_LENGTH = 13
UPC_A_LENGTH = 12
EAN_8_LENGTH = 8


def gs1_check_digit(body: str) -> int:
    """The check digit for `body` (all digits but the last): weights 3, 1, 3, ... from the
    right."""
    total = sum(int(digit) * (3 if i % 2 == 0 else 1) for i, digit in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def has_valid_check_digit(code: str) -> bool:
    return gs1_check_digit(code[:-1]) == int(code[-1])


def upc_e_to_upc_a(code: str) -> str | None:
    """The UPC-A code an 8-digit UPC-E code stands for (number system 0 or 1), else None."""
    number_system, digits, check = code[0], code[1:7], code[7]
    if number_system not in "01":
        return None
    d1, d2, d3, d4, d5, d6 = tuple(digits)
    if d6 in "012":
        middle = f"{d1}{d2}{d6}0000{d3}{d4}{d5}"
    elif d6 == "3":
        middle = f"{d1}{d2}{d3}00000{d4}{d5}"
    elif d6 == "4":
        middle = f"{d1}{d2}{d3}{d4}00000{d5}"
    else:
        middle = f"{d1}{d2}{d3}{d4}{d5}0000{d6}"
    return f"{number_system}{middle}{check}"


def normalize_barcode(text: str) -> str | None:
    """The barcode's canonical digits, or None if it is not a valid EAN-13, UPC-A, EAN-8 or
    UPC-E code. Whitespace is removed; EAN-13 stays as it is, UPC-A gets a leading 0, EAN-8
    stays 8 digits, and a UPC-E code (not valid as EAN-8) becomes the EAN-13 of its UPC-A
    expansion."""
    code = "".join(text.split())
    if not _DIGITS.fullmatch(code):
        return None
    if len(code) in (EAN_13_LENGTH, UPC_A_LENGTH):
        return code.zfill(EAN_13_LENGTH) if has_valid_check_digit(code) else None
    if len(code) == EAN_8_LENGTH:
        if has_valid_check_digit(code):
            return code
        upc_a = upc_e_to_upc_a(code)
        if upc_a is not None and has_valid_check_digit(upc_a):
            return upc_a.zfill(EAN_13_LENGTH)
    return None
