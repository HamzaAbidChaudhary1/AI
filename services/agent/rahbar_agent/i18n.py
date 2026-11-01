"""Server-side bilingual strings (case events, agent templates). UI strings live in apps/web/messages."""

from __future__ import annotations

from typing import Any

EVENTS: dict[str, tuple[str, str]] = {
    "case_created": ("Case opened for {service}.", "{service} کے لیے کیس کھولا گیا۔"),
    "assessed": ("Eligibility assessed: {rating}.", "اہلیت کا جائزہ مکمل: {rating_ur}۔"),
    "quoted": ("Itemised quote v{version} issued: {total}.", "تفصیلی قیمت نامہ v{version} جاری: {total}۔"),
    "quote_accepted": ("You accepted quote v{version}.", "آپ نے قیمت نامہ v{version} قبول کیا۔"),
    "documents_requested": ("Document checklist sent ({count} items).", "دستاویزات کی فہرست بھیجی گئی ({count} اشیاء)۔"),
    "document_uploaded": ("Document uploaded: {doc_type}.", "دستاویز اپ لوڈ ہوئی: {doc_type}۔"),
    "review_started": ("AI document review started.", "دستاویزات کی AI جانچ شروع ہوئی۔"),
    "review_done_ok": ("Document review passed with no blocking issues.", "دستاویزات کی جانچ مکمل، کوئی رکاوٹ نہیں۔"),
    "review_done_issues": ("Document review found {count} issue(s) to fix.", "دستاویزات کی جانچ میں {count} مسئلہ/مسائل ملے۔"),
    "pack_ready": ("Application pack prepared for your review.", "درخواست کا پیک آپ کے جائزے کے لیے تیار ہے۔"),
    "awaiting_confirmation": ("Waiting for your confirmation: {summary}", "آپ کی تصدیق کا انتظار: {summary}"),
    "user_confirmed": ("You confirmed: {summary}", "آپ نے تصدیق کی: {summary}"),
    "ops_approved": ("Our team approved: {summary}", "ہماری ٹیم نے منظوری دی: {summary}"),
    "ops_rejected": ("Our team did not approve this step: {reason}", "ہماری ٹیم نے یہ قدم منظور نہیں کیا: {reason}"),
    "submitted": ("Application submitted. Reference: {reference}", "درخواست جمع ہو گئی۔ حوالہ نمبر: {reference}"),
    "biometrics_scheduled": ("Biometrics appointment: {when} at {where}.", "بایومیٹرکس اپائنٹمنٹ: {when}، {where}۔"),
    "in_process": ("The embassy is processing the application.", "سفارت خانہ درخواست پر کارروائی کر رہا ہے۔"),
    "decision_approved": ("Decision received: visa issued.", "فیصلہ موصول: ویزا جاری ہو گیا۔"),
    "decision_refused": ("Decision received: visa refused. We'll explain the reasons.", "فیصلہ موصول: ویزا مسترد۔ ہم وجوہات سمجھائیں گے۔"),
    "payment_requested": ("Payment requested: {amount} by bank transfer.", "ادائیگی کی درخواست: {amount} بذریعہ بینک ٹرانسفر۔"),
    "payment_receipt": ("Payment receipt uploaded; our team will verify it.", "ادائیگی کی رسید اپ لوڈ ہو گئی؛ ہماری ٹیم تصدیق کرے گی۔"),
    "payment_verified": ("Payment of {amount} verified. Ref: {reference}", "{amount} کی ادائیگی کی تصدیق ہو گئی۔ حوالہ: {reference}"),
    "booking_held": ("{kind} held. Reference: {reference}", "{kind} ہولڈ پر۔ حوالہ: {reference}"),
    "booked": ("{kind} booked. Reference: {reference}", "{kind} بک ہو گیا۔ حوالہ: {reference}"),
    "voucher_delivered": ("{kind} document delivered: {name}", "{kind} کی دستاویز فراہم: {name}"),
    "refund_issued": ("Refund of {amount} issued. Reason: {reason}", "{amount} کی واپسی جاری۔ وجہ: {reason}"),
    "cancelled": ("Case cancelled. {reason}", "کیس منسوخ۔ {reason}"),
    "completed": ("Case completed.", "کیس مکمل۔"),
    "status_changed": ("Status changed to {status}.", "حیثیت تبدیل: {status}۔"),
    "ops_note": ("{note}", "{note}"),
}

RATING_UR = {"strong": "مضبوط", "fair": "مناسب", "weak": "کمزور"}
SERVICE_NAMES = {
    "visit_visa": ("visit visa", "وزٹ ویزا"), "umrah_package": ("Umrah package", "عمرہ پیکج"),
    "flight": ("flight", "فلائٹ"), "hotel": ("hotel", "ہوٹل"), "tour": ("tour plan", "ٹور پلان"),
    "scam_check": ("scam check", "اسکیم چیک"),
}
COUNTRY_NAMES = {
    "GB": ("United Kingdom", "برطانیہ"), "TR": ("Türkiye", "ترکیہ"), "DE": ("Germany (Schengen)", "جرمنی (Schengen)"),
    "AE": ("United Arab Emirates", "متحدہ عرب امارات"), "MY": ("Malaysia", "ملائیشیا"), "SA": ("Saudi Arabia", "سعودی عرب"),
    "CA": ("Canada", "کینیڈا"), "US": ("United States", "امریکہ"), "PK": ("Pakistan", "پاکستان"),
}
VISA_TYPES = {"GB": "visitor", "TR": "evisa", "DE": "schengen_c", "AE": "visit", "MY": "evisa", "SA": "tourist"}


def event_text(key: str, **kw: Any) -> tuple[str, str]:
    en, ur = EVENTS[key]
    if "rating" in kw:
        kw.setdefault("rating_ur", RATING_UR.get(kw["rating"], kw["rating"]))
    if "service" in kw and kw["service"] in SERVICE_NAMES:
        s_en, s_ur = SERVICE_NAMES[kw["service"]]
        return en.format(**{**kw, "service": s_en}), ur.format(**{**kw, "service": s_ur})
    return en.format(**kw), ur.format(**kw)


def country_name(code: str | None, locale: str = "en") -> str:
    if not code:
        return ""
    en, ur = COUNTRY_NAMES.get(code, (code, code))
    return ur if locale == "ur" else en
