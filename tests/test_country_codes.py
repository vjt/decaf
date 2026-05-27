"""Tests for ISO -> AdE country code mapping."""

from __future__ import annotations

from decaf.country_codes import iso_to_ade_country_code


def test_us_maps_to_069():
    assert iso_to_ade_country_code("US") == "069"


def test_ie_maps_to_040():
    assert iso_to_ade_country_code("IE") == "040"


def test_case_insensitive():
    assert iso_to_ade_country_code("us") == "069"
    assert iso_to_ade_country_code("Ie") == "040"


def test_unknown_returns_empty():
    assert iso_to_ade_country_code("ZZ") == ""
    assert iso_to_ade_country_code("") == ""


def test_uk_aliases_to_gb():
    assert iso_to_ade_country_code("GB") == "031"
    assert iso_to_ade_country_code("UK") == "031"


def test_all_codes_are_three_digits():
    """AdE codes are zero-padded 3-digit numerics — enforce shape so we
    catch typos like '40' instead of '040'."""
    from decaf.country_codes import ISO_TO_ADE

    for iso, code in ISO_TO_ADE.items():
        assert len(code) == 3, f"{iso} -> {code!r} is not 3 chars"
        assert code.isdigit(), f"{iso} -> {code!r} is not numeric"
