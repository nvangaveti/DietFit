"""Automated Test Suite for Abuse Protection & Rate Limiting Defense.

Tests:
1. AI Generation Request Throttling (Burst Limit)
2. External API Endpoint Limiting (USDA & Tavily)
3. Rate Limit Key Formatting
4. Rate Limit Resetting
"""

import sys
import os
import time

# Ensure workspace root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.ratelimit import (
    check_abuse_limit,
    record_abuse_call,
    reset_abuse_limit,
    enforce_abuse_limit,
    format_rate_limit_key,
    RateLimitExceeded,
    RATE_LIMIT_POLICIES
)


def test_ai_generation_rate_limiting():
    print("[TEST 1] Testing AI Generation Burst Throttling...")
    ident = f"user_ai_{time.time()}"
    reset_abuse_limit("ai_generation", ident)
    
    # AI generation policy allows 8 requests in 60s burst window
    for i in range(8):
        allowed, _ = check_abuse_limit("ai_generation", ident)
        assert allowed is True, f"AI generation run {i+1} should be allowed"
        record_abuse_call("ai_generation", ident)
        
    # 9th run must be throttled
    allowed, rem = check_abuse_limit("ai_generation", ident)
    assert allowed is False, "9th AI generation run must be blocked"
    assert rem > 0, f"Remaining lockout should be > 0, got {rem}"
    
    # Enforce should raise RateLimitExceeded
    try:
        enforce_abuse_limit("ai_generation", ident)
        assert False, "Should have raised RateLimitExceeded"
    except RateLimitExceeded as e:
        assert e.action == "ai_generation"
        assert e.retry_after_seconds > 0
    print("  --> [PASS] AI generation throttled after 8 burst calls; RateLimitExceeded exception raised.")


def test_api_query_rate_limiting():
    print("[TEST 2] Testing External API Query Limiting...")
    ident = f"usda_caller_{time.time()}"
    reset_abuse_limit("api_query", ident)
    
    # API query policy allows 20 calls
    for i in range(20):
        allowed, _ = check_abuse_limit("api_query", ident)
        assert allowed is True, f"API query {i+1} should be allowed"
        record_abuse_call("api_query", ident)
        
    # 21st call must be blocked
    allowed, rem = check_abuse_limit("api_query", ident)
    assert allowed is False, "21st API query must be blocked"
    assert rem > 0, "Remaining lockout should be > 0"
    print("  --> [PASS] External API queries capped at 20 calls per minute.")


def test_format_rate_limit_key():
    print("[TEST 3] Testing Rate Limit Key Formatting...")
    key1 = format_rate_limit_key("user@example.com", "gemini_vision")
    assert key1 == "user@example.com:gemini_vision"
    
    key2 = format_rate_limit_key(None, "api_query")
    assert key2 == "anonymous:api_query"
    print("  --> [PASS] Rate limit key formatting verified.")


def test_rate_limit_reset():
    print("[TEST 4] Testing Rate Limit Reset Mechanism...")
    ident = f"reset_tester_{time.time()}"
    reset_abuse_limit("ai_generation", ident)
    
    # Exhaust calls
    for _ in range(8):
        record_abuse_call("ai_generation", ident)
    allowed, _ = check_abuse_limit("ai_generation", ident)
    assert allowed is False, "Should be locked out"
    
    # Reset
    reset_abuse_limit("ai_generation", ident)
    allowed_after, _ = check_abuse_limit("ai_generation", ident)
    assert allowed_after is True, "Should be allowed after reset"
    print("  --> [PASS] Rate limit reset mechanism verified.")


if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING ABUSE PROTECTION & RATE LIMITING TEST SUITE")
    print("=" * 65)
    test_ai_generation_rate_limiting()
    test_api_query_rate_limiting()
    test_format_rate_limit_key()
    test_rate_limit_reset()
    print("=" * 65)
    print("ALL ABUSE PROTECTION TESTS PASSED!")
    print("=" * 65)
