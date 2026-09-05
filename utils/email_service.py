"""Enterprise Out-of-Band Email Service for DietFit.

Provides:
- Gmail SMTP & standard TLS/SSL SMTP relay integration
- HTML & plaintext responsive email templating
- Audit logging for operational emails
"""

import os
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple, Dict, Any

try:
    import streamlit as st
except ImportError:
    st = None

from utils.security_logger import (
    log_security_event,
    sanitize_log_string
)

EVENT_EMAIL_DISPATCHED = "EMAIL_DISPATCHED"
EVENT_EMAIL_FAILED = "EMAIL_FAILED"


def get_smtp_config() -> Dict[str, Any]:
    """Retrieves SMTP configuration from Streamlit secrets or system environment variables.
    
    Checks Streamlit secrets first, then falls back to environment variables.
    """
    config = {
        "host": "smtp.gmail.com",
        "port": 587,
        "user": "",
        "password": "",
        "from_name": "DietFit Security Matrix",
        "from_email": "",
        "use_tls": True,
        "use_ssl": False,
    }

    # 1. Inspect Streamlit secrets
    if st is not None:
        try:
            if hasattr(st, "secrets") and "smtp" in st.secrets:
                smtp_sec = st.secrets["smtp"]
                config["host"] = smtp_sec.get("host", config["host"])
                config["port"] = int(smtp_sec.get("port", config["port"]))
                config["user"] = smtp_sec.get("user", "")
                config["password"] = smtp_sec.get("password", "")
                config["from_name"] = smtp_sec.get("from_name", config["from_name"])
                config["from_email"] = smtp_sec.get("from_email", config["user"])
                config["use_tls"] = bool(smtp_sec.get("use_tls", True))
                config["use_ssl"] = bool(smtp_sec.get("use_ssl", False))
        except Exception:
            pass

    # 2. Inspect Environment Variables (overrides if present)
    env_user = os.environ.get("SMTP_USER") or os.environ.get("SMTP_EMAIL") or os.environ.get("GMAIL_USER")
    if env_user:
        config["user"] = env_user
        
    env_password = (
        os.environ.get("SMTP_PASSWORD") 
        or os.environ.get("SMTP_APP_PASSWORD") 
        or os.environ.get("GMAIL_APP_PASSWORD")
    )
    if env_password:
        config["password"] = env_password

    env_host = os.environ.get("SMTP_HOST") or os.environ.get("SMTP_SERVER")
    if env_host:
        config["host"] = env_host

    env_port = os.environ.get("SMTP_PORT")
    if env_port:
        try:
            config["port"] = int(env_port)
        except ValueError:
            pass

    env_from_name = os.environ.get("SMTP_FROM_NAME")
    if env_from_name:
        config["from_name"] = env_from_name

    if not config["from_email"]:
        config["from_email"] = config["user"]

    if config["port"] == 465:
        config["use_ssl"] = True
        config["use_tls"] = False

    return config


def is_smtp_configured() -> bool:
    """Verifies whether valid, non-placeholder SMTP credentials are configured."""
    cfg = get_smtp_config()
    user = cfg.get("user", "").strip()
    pwd = cfg.get("password", "").strip()
    
    if not user or not pwd:
        return False
        
    # Check for placeholder markers
    placeholders = ["YOUR_EMAIL", "YOUR_GMAIL", "YOUR_APP_PASSWORD", "EXAMPLE.COM", "YOUR_SMTP", "YOUR_GMAIL_ADDRESS"]
    if any(p in user.upper() or p in pwd.upper() for p in placeholders):
        return False
        
    return True


def send_email(
    to_email: str, 
    subject: str, 
    html_content: str, 
    text_content: str
) -> Tuple[bool, str]:
    """Transmits a MIME multipart (HTML + plaintext) email via authenticated SMTP.
    
    Returns:
        (success: bool, status_message: str)
    """
    cfg = get_smtp_config()
    if not is_smtp_configured():
        return False, "SMTP credentials are not configured. Please configure Gmail SMTP in secrets.toml or .env."

    sender = cfg["from_email"] or cfg["user"]
    sender_display = f"{cfg['from_name']} <{sender}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_display
    msg["To"] = to_email.strip()
    msg["X-Priority"] = "1"
    msg["Precedence"] = "bulk"

    part_text = MIMEText(text_content, "plain", "utf-8")
    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_text)
    msg.attach(part_html)

    try:
        timeout_seconds = 10
        if cfg["use_ssl"]:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=timeout_seconds)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=timeout_seconds)
            server.ehlo()
            if cfg["use_tls"]:
                server.starttls()
                server.ehlo()

        server.login(cfg["user"], cfg["password"])
        server.sendmail(sender, [to_email.strip()], msg.as_string())
        server.quit()

        log_security_event(
            EVENT_EMAIL_DISPATCHED,
            severity="INFO",
            actor=to_email.strip(),
            action_taken="DISPATCH_EMAIL",
            resource="smtp_mailer",
            details={"recipient": to_email.strip(), "subject": subject}
        )
        return True, "Email successfully dispatched."

    except smtplib.SMTPAuthenticationError as auth_err:
        log_security_event(
            EVENT_EMAIL_FAILED,
            severity="ERROR",
            actor=to_email.strip(),
            action_taken="FAIL_AUTH",
            resource="smtp_mailer",
            details={"error": sanitize_log_string(str(auth_err))}
        )
        return False, "Authentication failed with Gmail SMTP. Ensure you are using a 16-character Google App Password."

    except (socket.timeout, socket.gaierror) as net_err:
        log_security_event(
            EVENT_EMAIL_FAILED,
            severity="ERROR",
            actor=to_email.strip(),
            action_taken="NETWORK_TIMEOUT",
            resource="smtp_mailer",
            details={"error": sanitize_log_string(str(net_err))}
        )
        return False, f"SMTP Connection timed out or server unreachable: {net_err}"

    except Exception as e:
        log_security_event(
            EVENT_EMAIL_FAILED,
            severity="ERROR",
            actor=to_email.strip(),
            action_taken="DISPATCH_ERROR",
            resource="smtp_mailer",
            details={"error": sanitize_log_string(str(e))}
        )
        return False, f"Email delivery error: {e}"
