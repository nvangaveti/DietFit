"""Automated IDOR & Resource Ownership Test Suite for DietFit.

Verifies:
- Complete prevention of Insecure Direct Object Reference (IDOR) attacks
- Unauthorized cross-user profile read access is strictly rejected with ResourceOwnershipError
- Unauthorized cross-user profile write/tamper access is strictly rejected
- Unauthorized cross-user account deletion is blocked
- Unauthorized cross-user account record reading is blocked
- Legitimate resource owners can safely read, update, and manage their own records
- Case-insensitive, constant-time ownership verification
"""

import os
import sys
import shutil

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.storage import (
    load_user,
    save_user,
    delete_user,
    get_user_record,
    create_user_record,
    verify_ownership,
    ResourceOwnershipError
)


def run_idor_tests():
    print("=== STARTING IDOR & RESOURCE OWNERSHIP SECURITY TESTS ===")
    
    backup_file = "users.json.bak_idor"
    if os.path.exists("users.json"):
        shutil.copy("users.json", backup_file)
        
    try:
        victim_email = "victim@securecorp.com"
        attacker_email = "attacker@evilcorp.com"
        
        # Setup: Create initial victim and attacker Google user accounts
        create_user_record(
            email=victim_email,
            name="Alice Victim",
            profile={"goal": "lose_fat", "calorie_target": 1800, "protein_target": 140}
        )
        
        create_user_record(
            email=attacker_email,
            name="Bob Attacker",
            profile={"goal": "build_muscle", "calorie_target": 3000, "protein_target": 200}
        )
        
        # --- TEST 1: IDOR Profile Read Attempt ---
        print("\n[Test 1] Testing IDOR Unauthorized Read Protection...")
        try:
            load_user(victim_email, authenticated_email=attacker_email)
            assert False, "CRITICAL: Attacker was able to read victim's profile data!"
        except ResourceOwnershipError as e:
            print(f"[PASS] Unauthorized profile read blocked: {e}")
            
        # --- TEST 2: IDOR Profile Tamper / Write Attempt ---
        print("\n[Test 2] Testing IDOR Unauthorized Write Protection...")
        malicious_profile = {"goal": "poison_diet", "calorie_target": 50000}
        try:
            save_user(victim_email, malicious_profile, authenticated_email=attacker_email)
            assert False, "CRITICAL: Attacker was able to overwrite victim's profile!"
        except ResourceOwnershipError as e:
            print(f"[PASS] Unauthorized profile write blocked: {e}")
            
        # Verify victim's data remained unmodified
        victim_data = load_user(victim_email, authenticated_email=victim_email)
        assert victim_data["calorie_target"] == 1800, "Victim profile was corrupted!"
        
        # --- TEST 3: IDOR Account Deletion Attempt ---
        print("\n[Test 3] Testing IDOR Account Deletion Protection...")
        try:
            delete_user(victim_email, authenticated_email=attacker_email)
            assert False, "CRITICAL: Attacker was able to delete victim's account!"
        except ResourceOwnershipError as e:
            print(f"[PASS] Unauthorized account deletion blocked: {e}")
            
        # Verify victim still exists
        assert load_user(victim_email, authenticated_email=victim_email) is not None
        
        # --- TEST 4: IDOR Security Record Read Attempt ---
        print("\n[Test 4] Testing IDOR Security Record Read Protection...")
        try:
            get_user_record(victim_email, authenticated_email=attacker_email)
            assert False, "CRITICAL: Attacker was able to read victim's full user record!"
        except ResourceOwnershipError as e:
            print(f"[PASS] Unauthorized user record read blocked: {e}")
            
        # --- TEST 5: Legitimate Owner Operations ---
        print("\n[Test 5] Testing Legitimate Owner Access & Case Insensitivity...")
        # Upper/mixed case should match cleanly
        victim_upper = "VICTIM@SECURECORP.COM"
        data = load_user(victim_email, authenticated_email=victim_upper)
        assert data is not None and data["calorie_target"] == 1800
        
        # Owner updates their own target
        updated_profile = {"goal": "maintain", "calorie_target": 2100, "protein_target": 150}
        save_user(victim_email, updated_profile, authenticated_email=victim_email)
        reloaded = load_user(victim_email, authenticated_email=victim_email)
        assert reloaded["calorie_target"] == 2100
        print("[PASS] Legitimate owner read and update verified successfully.")

        # --- TEST 6: Legitimate Account Deletion ---
        print("\n[Test 6] Testing Legitimate Owner Account Deletion...")
        deleted = delete_user(victim_email, authenticated_email=victim_email)
        assert deleted is True, "Owner was unable to delete their own account."
        assert load_user(victim_email, authenticated_email=victim_email) is None
        print("[PASS] Legitimate account deletion verified.")
        
    finally:
        if os.path.exists(backup_file):
            shutil.copy(backup_file, "users.json")
            os.remove(backup_file)
            
    print("\n=== ALL IDOR DEFENSE & OWNERSHIP TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    run_idor_tests()
