"""Multi-Tier Abuse Prevention & Rate Limiting Engine.

Implements token-bucket and sliding-window rate limiting for:
- AI Generation Requests (Gemini vision & advisor: max 8 requests per minute)
- External API Endpoints (USDA & Tavily: max 20 requests per minute)
"""

import time
from typing import Tuple, Dict, List, Optional

# ==========================================
# DEFAULT POLICIES (Requests, Window in Seconds, Lockout in Seconds)
# ==========================================
RATE_LIMIT_POLICIES = {
    "ai_generation": {"max_calls": 8, "window": 60, "lockout": 60},     # 8 AI runs / min (burst limit)
    "api_query": {"max_calls": 20, "window": 60, "lockout": 60}        # 20 external API queries / min
}

# Global in-memory tracking: policy_name -> identifier -> list of timestamps
_BUCKETS: Dict[str, Dict[str, List[float]]] = {action: {} for action in RATE_LIMIT_POLICIES}
# Lockout tracking: policy_name -> identifier -> lockout_expiration_timestamp
_LOCKOUT_BUCKETS: Dict[str, Dict[str, float]] = {action: {} for action in RATE_LIMIT_POLICIES}


class RateLimitExceeded(Exception):
    """Raised when an operation exceeds its configured abuse limit."""
    def __init__(self, action: str, retry_after_seconds: int, message: Optional[str] = None):
        self.action = action
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message or f"Rate limit exceeded for '{action}'. Retry after {retry_after_seconds}s.")


def format_rate_limit_key(user_id: Optional[str], resource: str) -> str:
    """Combines an authenticated user identifier with a resource name for per-user rate limiting."""
    clean_user = str(user_id).strip().lower() if user_id else "anonymous"
    clean_res = str(resource).strip().lower()
    return f"{clean_user}:{clean_res}"


def check_abuse_limit(action: str, identifier: str) -> Tuple[bool, int]:
    """Checks if an identifier has exceeded the limit for a specific action.
    
    Args:
        action: The category ('ai_generation', 'api_query')
        identifier: The user email or composite per-user key (e.g. 'user@example.com:resource')
    Returns:
        (is_allowed: bool, remaining_lockout_seconds: int)
    """
    clean_action = action.lower()
    clean_id = str(identifier).strip().lower()
    now = time.time()
    
    if clean_action not in RATE_LIMIT_POLICIES:
        return True, 0
        
    policy = RATE_LIMIT_POLICIES[clean_action]
    lockouts = _LOCKOUT_BUCKETS[clean_action]
    buckets = _BUCKETS[clean_action]
    
    # 1. Check active lockout
    lockout_until = lockouts.get(clean_id)
    if lockout_until:
        if now < lockout_until:
            return False, int(lockout_until - now)
        else:
            del lockouts[clean_id]
            buckets.pop(clean_id, None)
            
    # 2. Check sliding window
    calls = buckets.get(clean_id, [])
    # Prune calls outside current window
    valid_calls = [t for t in calls if now - t < policy["window"]]
    buckets[clean_id] = valid_calls
    
    if len(valid_calls) >= policy["max_calls"]:
        # Trigger lockout
        lockout_time = now + policy["lockout"]
        lockouts[clean_id] = lockout_time
        return False, policy["lockout"]
        
    return True, 0


def record_abuse_call(action: str, identifier: str) -> Tuple[bool, int]:
    """Records an invocation for rate-limiting.
    
    Returns:
        (is_allowed_after: bool, remaining_lockout_seconds: int)
    """
    clean_action = action.lower()
    clean_id = str(identifier).strip().lower()
    now = time.time()
    
    if clean_action not in RATE_LIMIT_POLICIES:
        return True, 0
        
    buckets = _BUCKETS[clean_action]
    if clean_id not in buckets:
        buckets[clean_id] = []
        
    policy = RATE_LIMIT_POLICIES[clean_action]
    valid_calls = [t for t in buckets[clean_id] if now - t < policy["window"]]
    valid_calls.append(now)
    buckets[clean_id] = valid_calls
    
    if len(valid_calls) > policy["max_calls"]:
        _LOCKOUT_BUCKETS[clean_action][clean_id] = now + policy["lockout"]
        return False, policy["lockout"]
        
    return True, 0


def reset_abuse_limit(action: str, identifier: str) -> None:
    """Resets the abuse rate bucket for an identifier."""
    clean_action = action.lower()
    clean_id = str(identifier).strip().lower()
    
    if clean_action in _BUCKETS:
        _BUCKETS[clean_action].pop(clean_id, None)
    if clean_action in _LOCKOUT_BUCKETS:
        _LOCKOUT_BUCKETS[clean_action].pop(clean_id, None)


def enforce_abuse_limit(action: str, identifier: str) -> None:
    """Convenience assertion: raises RateLimitExceeded if action is rate limited or locked out."""
    allowed, cooldown = check_abuse_limit(action, identifier)
    if not allowed:
        raise RateLimitExceeded(action, cooldown)
    
    allowed_after, lockout = record_abuse_call(action, identifier)
    if not allowed_after:
        raise RateLimitExceeded(action, lockout)
