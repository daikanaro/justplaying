"""VIX loader tests — hermetic (fixture CSV + mocked HTTP transport)."""

import httpx
import pytest

from qt.data.vix import VixError, fetch_vix, parse_vix_csv

FIXTURE = (
    "DATE,OPEN,HIGH,LOW,CLOSE\n"
    "01/02/2024,13.20,14.24,13.10,14.20\n"
    "01/03/2024,14.30,14.50,13.90,14.04\n"
    "01/04/2024,14.10,14.60,13.95,14.13\n"
)


def test_parse_valid_csv() -> None:
    df = parse_vix_csv(FIXTURE)
    assert df.height == 3
    assert df.columns == ["date", "open", "high", "low", "close"]
    assert df.get_column("close").to_list() == [14.20, 14.04, 14.13]


@pytest.mark.parametrize(
    ("label", "body"),
    [
        ("wrong header", "DAY,O,H,L,C\n01/02/2024,1,2,0,1\n"),
        ("empty data", "DATE,OPEN,HIGH,LOW,CLOSE\n"),
        (
            "duplicate dates",
            "DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2024,13,14,13,14\n01/02/2024,13,14,13,14\n",
        ),
        (
            "descending dates",
            "DATE,OPEN,HIGH,LOW,CLOSE\n01/03/2024,13,14,13,14\n01/02/2024,13,14,13,14\n",
        ),
        (
            "non-positive close",
            "DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2024,13,14,13,0.0\n",
        ),
    ],
)
def test_invalid_csv_rejected(label: str, body: str) -> None:
    with pytest.raises(VixError):
        parse_vix_csv(body)


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_fetch_vix_success() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=FIXTURE))
    df = fetch_vix("https://example.test/vix.csv", client=_client(transport))
    assert df.height == 3


def test_fetch_vix_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(VixError, match="download failed"):
        fetch_vix("https://example.test/vix.csv", client=_client(transport))
