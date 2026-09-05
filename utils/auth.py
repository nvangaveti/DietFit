"""Enterprise Session Security & Inactivity Timeout Lifecycle for DietFit.

Implements:
- Strict session lifecycle management for authenticated users (wrapping st.user)
- Inactivity idle timeout enforcement (30 minutes)
- Absolute session lifetime enforcement (24 hours)
- Cryptographic session token generation
"""

import time
import secrets
from typing import Tuple, Dict, Any, Optional

# ==========================================
# CONSTANTS & SECURITY CONFIGURATION
# ==========================================
SESSION_INACTIVITY_TIMEOUT = 1800     # 30 minutes
SESSION_ABSOLUTE_TIMEOUT = 86400      # 24 hours


# ==========================================
# SESSION SECURITY & TIMEOUT LIFECYCLE
# ==========================================
def create_session(email: str, name: str, is_verified: bool = True) -> Dict[str, Any]:
    """Creates a secure session tracking object with cryptographic ID and activity timestamps."""
    now = time.time()
    return {
        "session_id": secrets.token_urlsafe(32),
        "email": email.strip().lower(),
        "user_name": name,
        "is_verified": is_verified,
        "created_at": now,
        "last_active": now
    }


def validate_session(session: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """Validates session freshness, checking inactivity (30m) and absolute expiration (24h) limits.
    
    Returns:
        (is_valid: bool, reason_message: str)
    """
    if not session or not isinstance(session, dict):
        return False, "No active session."
        
    now = time.time()
    created_at = session.get("created_at", 0)
    last_active = session.get("last_active", 0)
    
    # Check absolute lifetime (24 hours)
    if now - created_at > SESSION_ABSOLUTE_TIMEOUT:
        return False, "Session reached maximum duration (24 hours). Please sign in again."
        
    # Check inactivity idle timeout (30 minutes)
    if now - last_active > SESSION_INACTIVITY_TIMEOUT:
        return False, "Session expired due to inactivity (30 minutes). Please sign in again."
        
    return True, "Session active."


def touch_session(session: Dict[str, Any]) -> None:
    """Refreshes the session's last activity timestamp."""
    if session and isinstance(session, dict):
        session["last_active"] = time.time()
