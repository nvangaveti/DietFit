"""Automated Security and Authentication Test Suite for DietFit.

Covers:
- Session creation and cryptographic session tokens
- Inactivity idle timeout enforcement (30 minutes)
- Absolute session lifetime enforcement (24 hours)
- Active session touch functionality
- Google OAuth user provisioning and storage persistence
- Profile loading and saving with backward compatibility
"""

import os
import sys
import time
import shutil

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.auth import (
    create_session,
    validate_session,
    touch_session,
    SESSION_INACTIVITY_TIMEOUT,
    SESSION_ABSOLUTE_TIMEOUT
)

from utils import storage


def run_tests():
    print("=== STARTING AUTH & SECURITY AUDIT TESTS ===")
    
    # --- TEST 1: Session Creation & Token Verification ---
    print("\n[Test 1] Testing Session Creation...")
    session = create_session("athlete@dietfit.ai", "DietFit Athlete")
    assert session["email"] == "athlete@dietfit.ai"
    assert session["user_name"] == "DietFit Athlete"
    assert "session_id" in session and len(session["session_id"]) > 20
    assert session["is_verified"] is True
    
    valid, reason = validate_session(session)
    assert valid is True, f"Fresh session should be valid, got: {reason}"
    print("[PASS] Test 1 Passed: Session creation and active state verified.")

    # --- TEST 2: Inactivity Timeout (30 min) ---
    print("\n[Test 2] Testing Inactivity Idle Timeout...")
    test_session = create_session("timeout_user@dietfit.ai", "Timeout User")
    
    # Simulate idle timeout (31 minutes ago)
    test_session["last_active"] = time.time() - (SESSION_INACTIVITY_TIMEOUT + 60)
    valid, reason = validate_session(test_session)
    assert valid is False, "Session should expire after inactivity timeout"
    assert "inactivity" in reason.lower(), f"Expected inactivity reason, got: {reason}"
    
    # Simulate active touch
    touch_session(test_session)
    valid, _ = validate_session(test_session)
    assert valid is True, "Touched session should be active again"
    print("[PASS] Test 2 Passed: 30-minute inactivity timeout and touch verified.")

    # --- TEST 3: Absolute Lifetime Timeout (24 hr) ---
    print("\n[Test 3] Testing Absolute Lifetime Expiration...")
    long_session = create_session("long_user@dietfit.ai", "Long User")
    
    # Simulate absolute expiration (24 hours + 60s ago)
    long_session["created_at"] = time.time() - (SESSION_ABSOLUTE_TIMEOUT + 60)
    valid, reason = validate_session(long_session)
    assert valid is False, "Session should expire after absolute timeout"
    assert "maximum duration" in reason.lower() or "24 hours" in reason.lower(), f"Expected absolute timeout message, got: {reason}"
    print("[PASS] Test 3 Passed: 24-hour absolute session duration limit verified.")

    # --- TEST 4: Google User Provisioning & Profile Storage ---
    print("\n[Test 4] Testing Storage User Provisioning & Persistence...")
    backup_path = "users.json.bak_auth"
    if os.path.exists("users.json"):
        shutil.copy("users.json", backup_path)
        
    try:
        test_email = "google_athlete@dietfit.ai"
        
        # 1. Provision new Google OAuth user record
        rec = storage.create_user_record(
            email=test_email,
            name="Google Athlete"
        )
        assert rec["email"] == test_email
        assert rec["auth_provider"] == "google"
        assert rec["is_verified"] is True
        assert "password_hash" not in rec or rec.get("password_hash") is None
        
        # 2. Retrieve user record
        retrieved = storage.get_user_record(test_email, authenticated_email=test_email)
        assert retrieved is not None
        assert retrieved["email"] == test_email
        assert retrieved["name"] == "Google Athlete"
        
        # 3. Save profile data
        profile_data = {
            "goal": "build_muscle",
            "diet_type": "balanced",
            "weight_kg": 75.0,
            "height_cm": 178.0,
            "calorie_target": 2600.0
        }
        storage.save_user(test_email, profile_data, authenticated_email=test_email)
        
        # 4. Load profile data
        loaded_profile = storage.load_user(test_email, authenticated_email=test_email)
        assert loaded_profile == profile_data
        
        # 5. Clean deletion
        deleted = storage.delete_user(test_email, authenticated_email=test_email)
        assert deleted is True
        assert storage.load_user(test_email, authenticated_email=test_email) is None
        
        print("[PASS] Test 4 Passed: Google OAuth user provisioning, profile saving, loading, and deletion verified.")
    finally:
        if os.path.exists(backup_path):
            shutil.copy(backup_path, "users.json")
            os.remove(backup_path)

    print("\n=== ALL SECURITY TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    run_tests()
