import pytest
from rahbar_agent import crypto
from rahbar_agent.money import convert_minor, format_money


def test_convert_minor_rounds_half_up():
    # GBP 127.00 at 356.205 PKR -> 45238.035 -> 45238.04
    assert convert_minor(12700, "GBP", "PKR", {"GBP": "356.205"}) == 4523804
    assert convert_minor(500, "PKR", "PKR", {}) == 500


def test_convert_minor_requires_rate():
    with pytest.raises(ValueError):
        convert_minor(100, "USD", "PKR", {})
    with pytest.raises(ValueError):
        convert_minor(100, "USD", "PKR", {"USD": "0"})


def test_format_money_always_shows_code():
    assert format_money(1500000, "PKR") == "PKR 15,000"
    assert format_money(12750, "GBP") == "GBP 127.50"


def test_encrypt_roundtrip_and_rotation():
    k1 = "k1:" + "a" * 43 + "="
    import base64

    k1 = "k1:" + base64.b64encode(b"1" * 32).decode()
    k2 = "k2:" + base64.b64encode(b"2" * 32).decode()
    blob = crypto.encrypt("AB1234567", k1)
    assert blob.startswith(b"k1:") and b"AB1234567" not in blob
    # after rotation the old ciphertext still decrypts; new data uses k2
    assert crypto.decrypt(blob, f"{k2},{k1}") == "AB1234567"
    assert crypto.encrypt("x", f"{k2},{k1}").startswith(b"k2:")
    assert crypto.mask("AB1234567") == "*****4567"
