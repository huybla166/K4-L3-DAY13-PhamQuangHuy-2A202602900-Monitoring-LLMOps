from __future__ import annotations

import hashlib
import re

# Thứ tự quan trọng: chuỗi số dài nhất (thẻ 15–16 số) phải scrub trước, nếu không
# pattern CCCD/điện thoại có thể "cắn" một phần số thẻ và để lộ phần còn lại.
PII_PATTERNS: dict[str, str] = {
    "email": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    # Visa/Master 16 số (4-4-4-4) và Amex 15 số (4-6-5), cho phép dấu cách/gạch ngang
    "credit_card": (
        r"(?<!\d)(?:\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}|\d{4}[- ]?\d{6}[- ]?\d{5})(?!\d)"
    ),
    # CCCD 12 số, viết liền hoặc tách nhóm 3 bằng dấu cách/chấm
    "cccd": r"(?<!\d)(?:\d{12}|\d{3}[ .]\d{3}[ .]\d{3}[ .]\d{3})(?!\d)",
    # Di động/cố định VN: 0xxxxxxxxx, +84/84/(+84) xxxxxxxxx, cho phép dấu cách/chấm/gạch
    "phone_vn": r"(?<!\d)(?:\(\+84\)|\+84|84|0)(?:[ .-]?\d){9}(?!\d)",
    # Hộ chiếu VN: 1 chữ in hoa + 7 chữ số (vd B1234567)
    "passport_vn": r"\b[A-Z]\d{7}\b",
}
_COMPILED_PATTERNS = [(name, re.compile(pattern)) for name, pattern in PII_PATTERNS.items()]


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in _COMPILED_PATTERNS:
        safe = pattern.sub(f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
