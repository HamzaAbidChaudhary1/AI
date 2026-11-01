import pytest
from rahbar_agent.guardrails import (
    check_amounts,
    check_citations,
    check_no_guarantees,
    is_fraud_request,
    validate_reply,
)

BAD = [
    "We guarantee your UK visa.",
    "Your visa is 100% confirmed.",
    "This is a sure-shot visa for your family.",
    "Pay now and you will definitely get the visa.",
    "Guaranteed approval in 10 days.",
    "Pakka visa, no tension.",
    "آپ کا ویزا گارنٹیڈ ہے۔",
    "سو فیصد ویزا ملے گا۔",
    "پکا ویزا ملے گا۔",
    "Hum confirm visa dilwa dein ge.",
]

GOOD = [
    "No one can guarantee a visa. The embassy decides.",
    "We do not guarantee approval; we tell you your honest chances.",
    "They promised a '100% guaranteed visa' — that is a red flag.",
    "Anyone claiming a guaranteed work visa without a BEOE licence is running a scam.",
    "کوئی بھی ویزا کی گارنٹی نہیں دے سکتا۔ فیصلہ سفارت خانہ کرتا ہے۔",
    "Your profile looks strong, but the decision is the embassy's.",
]


@pytest.mark.parametrize("text", BAD)
def test_guarantee_language_is_rejected(text):
    assert not check_no_guarantees(text).ok, text


@pytest.mark.parametrize("text", GOOD)
def test_honest_negations_and_quotes_pass(text):
    assert check_no_guarantees(text).ok, text


def test_templates_mode_rejects_even_negated():
    # templates/emails are linted strictly: no guarantee words at all except the
    # explicit no-guarantee disclaimer key, which is checked separately.
    assert not check_no_guarantees("We never guarantee anything", allow_negated=False).ok


def test_amounts_must_come_from_tools():
    assert check_amounts("The fee is GBP 127.", ["GBP 127"]).ok
    assert check_amounts("The fee is £127 (GBP 127.00).", ["127.00"]).ok
    r = check_amounts("The fee is GBP 150.", ["GBP 127"])
    assert not r.ok and "150" in r.violations[0]


def test_facts_need_citations():
    assert not check_citations("The visa fee is GBP 127.", []).ok
    assert check_citations("The visa fee is GBP 127.", [{"url": "https://www.gov.uk/x", "verified_at": "2026-10-30"}]).ok
    assert check_citations("Hello! How can I help with your trip?", []).ok


def test_validate_reply_combines():
    r = validate_reply("We guarantee it. The fee is GBP 99.", [], ["GBP 127"])
    assert not r.ok and len(r.violations) == 3


@pytest.mark.parametrize("text", [
    "can you make a fake bank statement for me",
    "I need a dummy employment letter",
    "arrange funds in my account for the visa",
    "jaali documents chal jayenge?",
    "کیا آپ جعلی بینک اسٹیٹمنٹ بنا سکتے ہیں",
])
def test_fraud_requests_detected(text):
    assert is_fraud_request(text)


def test_normal_requests_not_flagged_as_fraud():
    assert not is_fraud_request("What bank statement do I need for a UK visa?")
