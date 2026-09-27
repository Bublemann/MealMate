"""Barcodes: EAN-13, EAN-8, UPC-A, UPC-E and their canonical form (BAR-01)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.barcodes import (
    gs1_check_digit,
    has_valid_check_digit,
    normalize_barcode,
    upc_e_to_upc_a,
)


@pytest.mark.parametrize(
    ("body", "check"),
    [("400638133393", 1), ("03600029145", 2), ("9638507", 4), ("000000000000", 0)],
)
def test_check_digit(body: str, check: int) -> None:
    assert gs1_check_digit(body) == check
    assert has_valid_check_digit(f"{body}{check}")
    assert not has_valid_check_digit(f"{body}{(check + 1) % 10}")


@pytest.mark.parametrize(
    ("upc_e", "upc_a"),
    [
        ("04252614", "042100005264"),
        ("01234565", "012345000065"),
        ("01234507", "012000003457"),
        ("01234537", "012300000457"),
        ("01234547", "012340000057"),
        ("11234597", "112345000097"),
        ("21234565", None),
    ],
)
def test_upc_e_expansion(upc_e: str, upc_a: str | None) -> None:
    assert upc_e_to_upc_a(upc_e) == upc_a


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4006381333931", "4006381333931"),  # EAN-13
        (" 4006381 333931\t", "4006381333931"),
        ("036000291452", "0036000291452"),  # UPC-A → its EAN-13
        ("96385074", "96385074"),  # EAN-8 stays 8 digits (GTIN-8)
        ("04252614", "0042100005264"),  # UPC-E (not a valid EAN-8) → EAN-13 of 042100005264
        ("06543217", "0065100004327"),  # UPC-E
        ("01234565", "01234565"),  # valid as EAN-8 and as UPC-E: EAN-8
        ("4006381333932", None),  # wrong check digit
        ("96385075", None),
        ("04252615", None),
        ("21234565", None),  # number system 2 is no UPC-E
        ("400638133393", None),  # 12 digits, wrong check digit
        ("1234567", None),
        ("40063813339310", None),  # 14 digits
        ("4006-381333931", None),
        ("", None),
        ("   ", None),
        ("٤٠٠٦٣٨١٣٣٣٩٣١", None),  # other scripts' digits
    ],
)
def test_normalize_barcode(text: str, expected: str | None) -> None:
    assert normalize_barcode(text) == expected


@pytest.mark.parametrize(
    ("one", "other"),
    [
        # UPC-A and its EAN-13 form (a leading 0).
        ("036000291452", "0036000291452"),
        ("012345000065", "0012345000065"),
        # UPC-E and its UPC-A expansion, and that one's EAN-13 form.
        ("04252614", "042100005264"),
        ("04252614", "0042100005264"),
        ("01234531", "012300000451"),
        ("06543217", "065100004327"),
    ],
)
def test_forms_of_one_product_normalise_equal(one: str, other: str) -> None:
    """One product can be stored only once, whichever form was typed or scanned."""
    assert normalize_barcode(one) is not None
    assert normalize_barcode(one) == normalize_barcode(other)


def test_an_ean_8_is_not_a_upc_e() -> None:
    """EAN-8 is its own number range: a code valid as both is not expanded."""
    assert normalize_barcode("01234565") != normalize_barcode("012345000065")


@given(
    st.sampled_from([7, 11, 12]).flatmap(lambda n: st.text("0123456789", min_size=n, max_size=n))
)
def test_codes_with_their_check_digit_are_valid(body: str) -> None:
    code = f"{body}{gs1_check_digit(body)}"
    expected = code if len(code) == 8 else code.zfill(13)
    assert normalize_barcode(code) == expected
    assert normalize_barcode(expected) == expected
    if len(code) > 8:
        wrong = f"{body}{(gs1_check_digit(body) + 1) % 10}"
        assert normalize_barcode(wrong) is None
