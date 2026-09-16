import pytest

from utils import pretty_bytes


@pytest.mark.parametrize(
    ("val", "expected"),
    [
        (None, "unknown"),
        ("abc", "unknown"),
        (512, "512 B"),
        ("2048", "2 KB"),
        ("1,048,576", "1.0 MB"),
        (1610612736, "1.5 GB"),
    ],
)
def test_pretty_bytes(val, expected):
    assert pretty_bytes(val) == expected
