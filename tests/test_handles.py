"""Handle parsing from URLs, @handles, and plain names."""
import pytest

from nichefit.data.apify import parse_handle


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://x.com/naval", "naval"),
        ("https://twitter.com/naval?lang=en", "naval"),
        ("http://x.com/Naval/", "Naval"),
        ("@naval", "naval"),
        ("naval", "naval"),
        ("  @naval  ", "naval"),
        ("x.com/elonmusk/status/123", "elonmusk"),
        ("", ""),
    ],
)
def test_parse_handle(raw, expected):
    assert parse_handle(raw) == expected
