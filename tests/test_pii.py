from app.pii import hash_user_id, scrub_text, summarize_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_email_with_plus_and_subdomain() -> None:
    out = scrub_text("CC: huy.pham+lab13@mail.vinuni.edu.vn please")
    assert "huy.pham" not in out
    assert "vinuni.edu.vn" not in out
    assert out == "CC: [REDACTED_EMAIL] please"


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_phone_with_country_code_variants() -> None:
    for phone_number in ("+84901234567", "84901234567", "(+84) 90 123 4567", "sdt:0987654321"):
        out = scrub_text(f"Goi {phone_number} nhe")
        assert "REDACTED_PHONE_VN" in out
        assert "901234567" not in out and "987654321" not in out


def test_scrub_cccd() -> None:
    for cccd in ("079204001234", "079 204 001 234", "079.204.001.234"):
        out = scrub_text(f"CCCD cua toi: {cccd}")
        assert cccd not in out
        assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111", "3782 822463 10005"):
        out = scrub_text(f"The: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        # Không để sót mẩu số nào (pattern CCCD/phone không được cắn một phần số thẻ)
        assert "1111" not in out and "10005" not in out


def test_scrub_passport_vn() -> None:
    out = scrub_text("Ho chieu B1234567 het han 2030")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT_VN" in out


def test_scrub_multiple_pii_in_one_message() -> None:
    out = scrub_text("Email a@b.com, SDT 0901234567, the 4111 1111 1111 1111")
    assert out == "Email [REDACTED_EMAIL], SDT [REDACTED_PHONE_VN], the [REDACTED_CREDIT_CARD]"


def test_scrub_keeps_non_pii_numbers() -> None:
    text = "P95 latency 1234 ms, 42 tokens, cost 0.0021 USD, version 2026.09"
    assert scrub_text(text) == text


def test_summarize_text_scrubs_and_truncates() -> None:
    out = summarize_text("Phone 0901234567 " + "x" * 200, max_len=40)
    assert "0901234567" not in out
    assert out.endswith("...")
    assert len(out) == 43


def test_hash_user_id_is_stable_and_not_raw() -> None:
    assert hash_user_id("u01") == hash_user_id("u01")
    assert hash_user_id("u01") != hash_user_id("u02")
    assert "u01" not in hash_user_id("u01")
    assert len(hash_user_id("u01")) == 12
