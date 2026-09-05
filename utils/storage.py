"""Persistent Storage and User Data Management for DietFit.

Provides:
- Strict Resource Ownership Enforcement & IDOR Prevention (timing-safe verification)
- User profile and account persistence for Streamlit Google OAuth identities
- Backward compatibility with legacy profile storage
- Atomic and safe JSON persistence
"""

import os
import json
import time
import hmac
from typing import Optional, Dict, Any

USERS_FILE = "users.json"


# ==========================================
# 0. RESOURCE OWNERSHIP & IDOR DEFENSE
# ==========================================
from utils.security_logger import (
    log_security_event, EVENT_IDOR_BLOCKED
)

class ResourceOwnershipError(PermissionError):
    """Raised when an operation attempts to read, mutate, or delete a resource without ownership authorization."""
    pass


def verify_ownership(authenticated_identity: Optional[str], target_resource_owner: str) -> None:
    """Validates that the authenticated actor owns the requested resource using constant-time comparison.
    
    Args:
        authenticated_identity: The verified email/identity of the currently logged-in user (from st.user.email).
                                If None, indicates an internal system lookup.
        target_resource_owner: The owner of the resource being accessed.
    Raises:
        ResourceOwnershipError: If authenticated_identity does not strictly match target_resource_owner.
    """
    if authenticated_identity is None:
        return
        
    clean_auth = authenticated_identity.strip().lower()
    clean_target = target_resource_owner.strip().lower()
    
    # Timing-safe constant-time string comparison to prevent side-channel timing attacks
    if not hmac.compare_digest(clean_auth, clean_target):
        log_security_event(
            event_type=EVENT_IDOR_BLOCKED,
            severity="WARNING",
            actor=authenticated_identity,
            action_taken="DENY_403",
            resource=f"user_resource:{target_resource_owner}",
            details={"attempted_target": target_resource_owner}
        )
        raise ResourceOwnershipError(
            f"Security Alert [IDOR Blocked]: Authenticated session '{authenticated_identity}' "
            f"is unauthorized to access or mutate resource owned by '{target_resource_owner}'."
        )


def _read_db() -> Dict[str, Any]:
    """Reads the JSON storage file safely."""
    if not os.path.exists(USERS_FILE):
        return {"users": {}}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"users": {}}
            return json.loads(content)
    except Exception:
        return {"users": {}}


def _write_db(data: Dict[str, Any]) -> None:
    """Writes to the JSON storage file atomically with restricted permissions."""
    temp_file = f"{USERS_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    # Enforce restrictive file permissions (read/write only by owner: 0600) on POSIX
    try:
        if hasattr(os, "chmod"):
            os.chmod(temp_file, 0o600)
    except Exception:
        pass

    os.replace(temp_file, USERS_FILE)

    try:
        if hasattr(os, "chmod"):
            os.chmod(USERS_FILE, 0o600)
    except Exception:
        pass


# ==========================================
# 1. PROFILE METHODS (GUARDED AGAINST IDOR)
# ==========================================
def load_user(email: str, authenticated_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads the diet and fitness profile dict for a given user email/identifier.
    
    Enforces ownership validation if authenticated_email is provided.
    Maintains 100% backward-compatibility with legacy flat profile structures.
    """
    if not email:
        return None
        
    # Enforce IDOR ownership check
    verify_ownership(authenticated_email, email)
    
    db = _read_db()
    users = db.get("users", {})
    clean_email = email.strip().lower()
    
    user_data = users.get(clean_email) or users.get(email.strip())
    if not user_data:
        return None
        
    # Structured format
    if isinstance(user_data, dict) and "profile" in user_data:
        return user_data["profile"]
        
    # Legacy flat dictionary format
    return user_data


def save_user(email: str, profile: Dict[str, Any], authenticated_email: Optional[str] = None) -> None:
    """Saves or updates the diet and fitness profile for a given user email.
    
    Enforces ownership validation if authenticated_email is provided.
    """
    if not email:
        return
        
    # Enforce IDOR ownership check
    verify_ownership(authenticated_email, email)
    
    db = _read_db()
    if "users" not in db:
        db["users"] = {}
        
    clean_email = email.strip().lower()
    existing = db["users"].get(clean_email)
    
    if existing and isinstance(existing, dict):
        existing["profile"] = profile
        db["users"][clean_email] = existing
    else:
        # Check if legacy key exists
        if clean_email in db["users"]:
            db["users"][clean_email] = profile
        elif email.strip() in db["users"]:
            db["users"][email.strip()] = profile
        else:
            # New user entry with standard schema wrapper
            db["users"][clean_email] = {
                "email": clean_email,
                "name": clean_email.split("@")[0],
                "auth_provider": "google",
                "is_verified": True,
                "created_at": time.time(),
                "profile": profile
            }
            
    _write_db(db)


def delete_user(email: str, authenticated_email: str) -> bool:
    """Permanently deletes a user account and profile data.
    
    Strictly enforces that authenticated_email matches email.
    """
    if not email or not authenticated_email:
        return False
        
    # Strict IDOR ownership check
    verify_ownership(authenticated_email, email)
    
    clean_email = email.strip().lower()
    db = _read_db()
    users = db.get("users", {})
    
    deleted = False
    if clean_email in users:
        del users[clean_email]
        deleted = True
    elif email.strip() in users:
        del users[email.strip()]
        deleted = True
        
    if deleted:
        _write_db(db)
        return True
    return False


# ==========================================
# 2. USER RECORD MANAGEMENT
# ==========================================
def get_user_record(email: str, authenticated_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves the full account record for an email.
    
    If authenticated_email is provided, strictly enforces ownership check.
    """
    if not email:
        return None
        
    # Enforce IDOR ownership check if an authenticated session context is supplied
    verify_ownership(authenticated_email, email)
    
    db = _read_db()
    users = db.get("users", {})
    clean_email = email.strip().lower()
    
    record = users.get(clean_email) or users.get(email.strip())
    if not record or not isinstance(record, dict):
        return None
        
    # If legacy flat profile, normalize into full record
    if "profile" not in record:
        return {
            "email": clean_email,
            "name": clean_email.split("@")[0],
            "auth_provider": "google",
            "is_verified": True,
            "created_at": time.time(),
            "profile": record
        }
        
    return record


def create_user_record(
    email: str,
    name: str,
    profile: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Creates and persists a new authenticated Google user record (no password credentials)."""
    clean_email = email.strip().lower()
    db = _read_db()
    if "users" not in db:
        db["users"] = {}
        
    user_record = {
        "email": clean_email,
        "name": name.strip(),
        "auth_provider": "google",
        "is_verified": True,
        "created_at": time.time(),
        "profile": profile
    }
    db["users"][clean_email] = user_record
    _write_db(db)
    return user_record
