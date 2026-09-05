"""Enterprise Security Auditing & Logging Engine for DietFit.

Provides structured, tamper-resistant logging for:
- Authentication events (successful logins, failed attempts, brute-force lockouts)
- Authorization & IDOR violations
- Bot / scraper activity & honeypot triggers
- Unusual traffic patterns & rate limiting throttles
- External API errors & degradation
- Anti-Log-Injection / CRLF sanitization
- SIEM-compatible JSON Lines & rotating text logs
"""

import os
import re
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# ==========================================
# CONFIGURATION & DIRECTORY SETUP
# ==========================================
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

SECURITY_LOG_FILE = os.path.join(LOG_DIR, "security.log")
SECURITY_JSONL_FILE = os.path.join(LOG_DIR, "security_audit.jsonl")

# Standard Event Categories
EVENT_AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
EVENT_AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
EVENT_AUTH_LOCKOUT = "AUTH_LOCKOUT"
EVENT_AUTH_REGISTER = "AUTH_REGISTER_SUCCESS"
EVENT_AUTH_REGISTER_THROTTLED = "AUTH_REGISTER_THROTTLED"
EVENT_AUTH_RESET_REQUEST = "AUTH_RESET_REQUEST"
EVENT_AUTH_RESET_SUCCESS = "AUTH_RESET_SUCCESS"
EVENT_IDOR_BLOCKED = "IDOR_ATTEMPT_BLOCKED"
EVENT_BOT_HONEYPOT = "BOT_HONEYPOT_TRIGGERED"
EVENT_ABUSE_THROTTLED = "ABUSE_RATE_THROTTLED"
EVENT_API_ERROR = "API_ERROR"
EVENT_VALIDATION_FAILURE = "INPUT_VALIDATION_FAILURE"
EVENT_INSECURE_PROTOCOL = "INSECURE_PROTOCOL_DETECTED"
EVENT_EMAIL_OTP_DISPATCHED = "EMAIL_OTP_DISPATCHED"
EVENT_EMAIL_OTP_FAILED = "EMAIL_OTP_FAILED"

# ==========================================
# 1. ANTI-LOG-INJECTION / CRLF SANITIZATION
# ==========================================
def sanitize_log_string(val: Any) -> str:
    """Neutralizes Log Injection (CRLF / Log Forging) attacks.
    
    Prevents attackers from injecting fake log entries or breaking log
    parsers by stripping newline (\n), carriage return (\r), null bytes,
    and control characters.
    """
    if val is None:
        return "None"
    s = str(val)
    # Replace CRLF and control characters with sanitized space
    sanitized = re.sub(r"[\r\n\x00-\x1f\x7f-\x9f]", " ", s)
    return sanitized.strip()


def sanitize_dict_for_logging(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitizes dictionary keys and values for secure logging."""
    if not data or not isinstance(data, dict):
        return {}
    clean = {}
    for k, v in data.items():
        clean_key = sanitize_log_string(k)
        if isinstance(v, dict):
            clean[clean_key] = sanitize_dict_for_logging(v)
        elif isinstance(v, list):
            clean[clean_key] = [sanitize_log_string(item) if not isinstance(item, (int, float, bool)) else item for item in v]
        elif isinstance(v, (int, float, bool)):
            clean[clean_key] = v
        else:
            clean[clean_key] = sanitize_log_string(v)
    return clean


# ==========================================
# 2. LOGGING HANDLER INITIALIZATION
# ==========================================
_sec_logger = logging.getLogger("dietfit_security")
_sec_logger.setLevel(logging.INFO)

# Avoid duplicate handlers if reloaded in Streamlit
if not _sec_logger.handlers:
    # 1. Standard Rotating File Handler (Human-readable text)
    file_handler = RotatingFileHandler(
        SECURITY_LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=5,
        encoding="utf-8"
    )
    formatter = logging.Formatter(
        "[%(asctime)s UTC] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    _sec_logger.addHandler(file_handler)

    # 2. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _sec_logger.addHandler(console_handler)


# ==========================================
# 3. STRUCTURED EVENT EMISSION
# ==========================================
def log_security_event(
    event_type: str,
    severity: str,
    actor: str,
    action_taken: str,
    details: Optional[Dict[str, Any]] = None,
    resource: str = "application"
) -> Dict[str, Any]:
    """Records a structured security event, sanitizing all input and writing to both
    rotating text log and SIEM-compatible JSONL audit file.
    
    Args:
        event_type: Category identifier (e.g. AUTH_LOGIN_SUCCESS, ABUSE_RATE_THROTTLED)
        severity: 'INFO', 'WARNING', 'ERROR', or 'CRITICAL'
        actor: Authenticated email, IP, or session ID
        action_taken: 'ALLOW', 'DENY_403', 'LOCKOUT', 'THROTTLE', etc.
        details: Additional context metadata dictionary
        resource: Target resource or endpoint
    """
    clean_event = sanitize_log_string(event_type).upper()
    clean_sev = sanitize_log_string(severity).upper()
    clean_actor = sanitize_log_string(actor)
    clean_action = sanitize_log_string(action_taken)
    clean_resource = sanitize_log_string(resource)
    clean_details = sanitize_dict_for_logging(details)

    timestamp = datetime.now(timezone.utc).isoformat()

    event_payload = {
        "timestamp": timestamp,
        "event_type": clean_event,
        "severity": clean_sev,
        "actor": clean_actor,
        "resource": clean_resource,
        "action_taken": clean_action,
        "details": clean_details
    }

    # 1. Emit to text logger with format
    log_msg = (
        f"EVENT={clean_event} | ACTOR={clean_actor} | ACTION={clean_action} | "
        f"RESOURCE={clean_resource} | DETAILS={json.dumps(clean_details)}"
    )

    if clean_sev == "CRITICAL":
        _sec_logger.critical(log_msg)
    elif clean_sev == "ERROR":
        _sec_logger.error(log_msg)
    elif clean_sev == "WARNING":
        _sec_logger.warning(log_msg)
    else:
        _sec_logger.info(log_msg)

    # 2. Append to SIEM JSONL audit log
    try:
        with open(SECURITY_JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_payload) + "\n")
    except Exception as e:
        _sec_logger.error(f"Failed to append to security_audit.jsonl: {e}")

    return event_payload
