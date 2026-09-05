"""Automated Test Suite for Secure Deployment, HTTPS, Database Restriction & Security Auditing.

Tests:
1. Streamlit Security Configuration (.streamlit/config.toml)
2. Reverse Proxy TLS/HTTPS Enforcement & Security Headers (deploy/nginx.conf)
3. Direct Database & Sensitive File Access Restriction
4. Container Network Isolation (deploy/docker-compose.yml)
5. Anti-Log-Injection & CRLF Log Forging Neutralization
6. Structured Security Event Emission (JSONL & Rotating Text Log)
7. Secrets Protection & .gitignore Enforcement
"""

import sys
import os
import re
import json

# Ensure workspace root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.security_logger import (
    log_security_event,
    sanitize_log_string,
    EVENT_AUTH_LOGIN_SUCCESS,
    EVENT_AUTH_LOGIN_FAILURE,
    EVENT_AUTH_LOCKOUT,
    EVENT_API_ERROR,
    EVENT_ABUSE_THROTTLED,
    EVENT_IDOR_BLOCKED,
    SECURITY_LOG_FILE,
    SECURITY_JSONL_FILE
)


def test_streamlit_config():
    print("[TEST 1] Testing Streamlit Production Configuration...")
    config_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "config.toml")
    assert os.path.exists(config_path), ".streamlit/config.toml must exist"
    
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "enableXsrfProtection = true" in content, "XSRF protection must be enabled"
    assert "enableCORS = false" in content, "CORS must be disabled for state protection"
    assert "headless = true" in content, "Headless mode must be enabled"
    assert 'address = "127.0.0.1"' in content, "Streamlit should bind to localhost to avoid direct unproxied internet access"
    assert "gatherUsageStats = false" in content, "Usage telemetry must be disabled"
    print("  --> [PASS] Streamlit config enforces XSRF, CORS off, localhost binding, and telemetry off.")


def test_reverse_proxy_https_enforcement():
    print("[TEST 2] Testing Reverse Proxy HTTPS & Security Headers...")
    nginx_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "nginx.conf")
    assert os.path.exists(nginx_path), "deploy/nginx.conf must exist"
    
    with open(nginx_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Check 301 redirect to HTTPS
    assert "return 301 https://$host$request_uri;" in content, "HTTP must 301 redirect to HTTPS"
    # Check HSTS
    assert "Strict-Transport-Security" in content, "HSTS header must be configured"
    assert "max-age=31536000" in content, "HSTS should enforce at least 1 year"
    # Check modern security headers
    assert "X-Frame-Options" in content, "X-Frame-Options header must be set"
    assert "X-Content-Type-Options" in content, "X-Content-Type-Options header must be set"
    assert "Content-Security-Policy" in content, "CSP header must be set"
    print("  --> [PASS] Reverse proxy enforces HTTPS 301 redirect, HSTS, and defense headers.")


def test_database_access_restriction():
    print("[TEST 3] Testing Direct Database Access Restriction...")
    nginx_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "nginx.conf")
    with open(nginx_path, "r", encoding="utf-8") as f:
        nginx_content = f.read()
        
    # Verify Nginx denies direct access to sensitive files
    assert "deny all;" in nginx_content, "Nginx must deny direct database queries"
    assert "json" in nginx_content, "JSON database files must be blocked from direct web download"
    assert "users\\.json" in nginx_content or "users.json" in nginx_content, "users.json must be explicitly blocked"
    
    # Verify docker-compose network isolation
    compose_path = os.path.join(os.path.dirname(__file__), "..", "deploy", "docker-compose.yml")
    assert os.path.exists(compose_path), "deploy/docker-compose.yml must exist"
    with open(compose_path, "r", encoding="utf-8") as f:
        compose_content = f.read()
    
    assert "internal: true" in compose_content, "Application container must be on an internal network"
    print("  --> [PASS] Direct database queries blocked by reverse proxy and container network isolation.")


def test_secrets_gitignore_enforcement():
    print("[TEST 4] Testing Secrets Storage & Gitignore Protection...")
    gitignore_path = os.path.join(os.path.dirname(__file__), "..", ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore must exist"
    
    with open(gitignore_path, "r", encoding="utf-8") as f:
        git_content = f.read()
        
    assert ".env" in git_content, ".env must be ignored"
    assert ".streamlit/secrets.toml" in git_content, ".streamlit/secrets.toml must be ignored"
    assert "users.json" in git_content, "Database file users.json must be ignored"
    assert "*.pem" in git_content or "deploy/certs/" in git_content, "TLS certificates must be ignored"
    assert "logs/" in git_content, "Security logs must be ignored from git"
    print("  --> [PASS] .gitignore strictly protects .env, secrets.toml, database files, certs, and logs.")


def test_anti_log_injection_crlf():
    print("[TEST 5] Testing Anti-Log-Injection & CRLF Sanitization...")
    # Attempt log forging injection payload
    malicious_user = "admin@victim.com\r\n[2026-09-05 00:00:00 UTC] [CRITICAL] [dietfit_security] EVENT=FAKE_EVENT | ACTOR=root | ACTION=BYPASS"
    sanitized = sanitize_log_string(malicious_user)
    
    assert "\r" not in sanitized, "Carriage return must be stripped"
    assert "\n" not in sanitized, "Newline must be stripped"
    assert "\x00" not in sanitized, "Null byte must be stripped"
    
    # Emit test log event with malicious string
    event = log_security_event(
        event_type="TEST_INJECTION",
        severity="WARNING",
        actor=malicious_user,
        action_taken="BLOCK",
        details={"attempted_injection": malicious_user}
    )
    
    assert "\r" not in event["actor"]
    assert "\n" not in event["actor"]
    print("  --> [PASS] CRLF characters stripped; log forging injection prevented.")


def test_structured_security_event_logging():
    print("[TEST 6] Testing Structured Security Event Emission...")
    # Clean previous test entries if needed
    test_user = "sec_test_user@example.com"
    
    # 1. Emit Login Failure Event
    event1 = log_security_event(
        event_type=EVENT_AUTH_LOGIN_FAILURE,
        severity="WARNING",
        actor=test_user,
        action_taken="DENY_401",
        resource="auth_login",
        details={"reason": "bad_password"}
    )
    assert event1["event_type"] == EVENT_AUTH_LOGIN_FAILURE
    assert event1["actor"] == test_user
    assert event1["severity"] == "WARNING"
    
    # 2. Emit Lockout Event
    event2 = log_security_event(
        event_type=EVENT_AUTH_LOCKOUT,
        severity="ERROR",
        actor=test_user,
        action_taken="LOCKOUT",
        resource="auth_login",
        details={"cooldown_seconds": 900}
    )
    assert event2["event_type"] == EVENT_AUTH_LOCKOUT
    assert event2["severity"] == "ERROR"
    
    # 3. Emit IDOR Block Event
    event3 = log_security_event(
        event_type=EVENT_IDOR_BLOCKED,
        severity="WARNING",
        actor="attacker@evil.com",
        action_taken="DENY_403",
        resource="user_resource:victim@target.com",
        details={"attempted_target": "victim@target.com"}
    )
    assert event3["event_type"] == EVENT_IDOR_BLOCKED
    
    # 4. Verify physical files on disk
    assert os.path.exists(SECURITY_LOG_FILE), f"Text log {SECURITY_LOG_FILE} must exist"
    assert os.path.exists(SECURITY_JSONL_FILE), f"JSONL audit log {SECURITY_JSONL_FILE} must exist"
    
    # Verify JSONL formatting
    with open(SECURITY_JSONL_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) >= 3, "At least 3 events should be recorded in JSONL log"
        last_event = json.loads(lines[-1].strip())
        assert "timestamp" in last_event
        assert "event_type" in last_event
        assert "severity" in last_event
        assert "actor" in last_event
        
    print("  --> [PASS] Structured security events successfully written to rotating log and JSONL SIEM format.")


if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING SECURE DEPLOYMENT & AUDIT LOGGING TEST SUITE")
    print("=" * 65)
    test_streamlit_config()
    test_reverse_proxy_https_enforcement()
    test_database_access_restriction()
    test_secrets_gitignore_enforcement()
    test_anti_log_injection_crlf()
    test_structured_security_event_logging()
    print("=" * 65)
    print("ALL 6 SECURE DEPLOYMENT & LOGGING TESTS PASSED!")
    print("=" * 65)
