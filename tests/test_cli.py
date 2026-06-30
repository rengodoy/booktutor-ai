import pytest

from glyph.cli import _parse_pages, build_parser


def test_parse_single_page():
    assert _parse_pages("5") == [5]


def test_parse_range():
    assert _parse_pages("51-60") == list(range(51, 61))


def test_parse_mixed_dedup_sorted():
    assert _parse_pages("1-3,7,10-12,2") == [1, 2, 3, 7, 10, 11, 12]


def test_parse_whitespace_tolerated():
    assert _parse_pages(" 3 - 5 , 9 ") == [3, 4, 5, 9]


@pytest.mark.parametrize("bad", ["0", "10-5", "-3", "abc", "", ","])
def test_parse_rejects_bad(bad):
    with pytest.raises(ValueError):
        _parse_pages(bad)


def test_no_escalate_flag_defaults_false():
    args = build_parser().parse_args(["extract", "book.pdf"])
    assert args.no_escalate is False


def test_no_escalate_flag_set():
    args = build_parser().parse_args(["extract", "book.pdf", "--no-escalate"])
    assert args.no_escalate is True
