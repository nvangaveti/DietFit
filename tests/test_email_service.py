"""Automated Test Suite for Out-of-Band Email Service.

Tests:
1. SMTP Configuration Loading & Defaults
2. Placeholder Detection & is_smtp_configured Validation
3. Sending Email via Mocked SMTP
4. Graceful failure when SMTP is not configured
5. SMTP Authentication failure handling
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.email_service import (
    get_smtp_config,
    is_smtp_configured,
    send_email
)


class TestEmailService(unittest.TestCase):

    def setUp(self):
        # Clear env variables before each test
        for var in ["SMTP_USER", "SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM_NAME"]:
            if var in os.environ:
                del os.environ[var]

    def test_placeholder_detection(self):
        """Placeholder values should not be considered valid SMTP credentials."""
        with patch.dict(os.environ, {
            "SMTP_USER": "YOUR_GMAIL_ADDRESS@gmail.com",
            "SMTP_PASSWORD": "YOUR_GMAIL_16_CHAR_APP_PASSWORD"
        }):
            self.assertFalse(is_smtp_configured())

    def test_valid_smtp_configured_detection(self):
        """Real credentials should evaluate to True."""
        with patch.dict(os.environ, {
            "SMTP_USER": "support@dietfit-matrix.org",
            "SMTP_PASSWORD": "abcd efgh ijkl mnop"
        }):
            self.assertTrue(is_smtp_configured())

    def test_unconfigured_send_fails_gracefully(self):
        """Calling send_email without configured SMTP should return False and not raise uncaught errors."""
        with patch.dict(os.environ, {"SMTP_USER": "", "SMTP_PASSWORD": ""}):
            success, msg = send_email("target@test.com", "Test Subject", "<p>Test</p>", "Test")
            self.assertFalse(success)
            self.assertIn("not configured", msg.lower())

    @patch("smtplib.SMTP")
    def test_send_email_mocked_smtp(self, mock_smtp_cls):
        """Email dispatch properly connects, authenticates, and sends via SMTP."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        with patch.dict(os.environ, {
            "SMTP_USER": "admin@dietfit-matrix.org",
            "SMTP_PASSWORD": "real_password_token",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587"
        }):
            success, msg = send_email("athlete@example.com", "DietFit Notice", "<b>Hello</b>", "Hello")
            self.assertTrue(success)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("admin@dietfit-matrix.org", "real_password_token")
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_smtp_auth_failure_handling(self, mock_smtp_cls):
        """Authentication error from Gmail is handled cleanly with actionable message."""
        import smtplib
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp_cls.return_value = mock_server

        with patch.dict(os.environ, {
            "SMTP_USER": "admin@dietfit-matrix.org",
            "SMTP_PASSWORD": "wrong_password",
            "SMTP_HOST": "smtp.gmail.com"
        }):
            success, msg = send_email("target@example.com", "Alert", "<b>Body</b>", "Body")
            self.assertFalse(success)
            self.assertIn("authentication failed", msg.lower())


if __name__ == "__main__":
    unittest.main()
