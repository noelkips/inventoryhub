from __future__ import annotations

from typing import Iterable

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


def _is_test_db() -> bool:
    """
    Treat the hosted test site as a "redirect all emails" environment.

    Trigger rule requested:
    - If DB is `ufdxwals_it_test_db`, redirect all outgoing emails.
    """
    db_name_config = getattr(settings, "DB_NAME_CONFIG", None)
    if db_name_config == "ufdxwals_it_test_db":
        return True

    try:
        db_name = settings.DATABASES.get("default", {}).get("NAME")
    except Exception:
        db_name = None
    return db_name == "ufdxwals_it_test_db"


def _redirect_to() -> list[str]:
    redirect_to = getattr(settings, "TEST_EMAIL_RECIPIENT", None)
    if not redirect_to:
        return []
    return [redirect_to]


def _redirect_cc() -> list[str]:
    cc = getattr(settings, "TEST_EMAIL_CC", None)
    if not cc:
        return []
    return list(cc)


class RedirectingSMTPEmailBackend(SMTPEmailBackend):
    """
    SMTP backend that *redirects all outgoing mail* when running against the test DB.

    This catches:
    - `send_mail(...)`
    - `EmailMessage(...)`
    - `EmailMultiAlternatives(...)`
    - any other Django email uses (as long as they go through EMAIL_BACKEND)
    """

    def send_messages(self, email_messages: Iterable) -> int:
        if not email_messages:
            return 0

        if not _is_test_db():
            return super().send_messages(email_messages)

        redirect_to = _redirect_to()
        if not redirect_to:
            # Fail-safe: if redirect isn't configured, do not send anything on test DB.
            return 0

        redirect_cc = _redirect_cc()

        for message in email_messages:
            original_to = list(getattr(message, "to", []) or [])
            original_cc = list(getattr(message, "cc", []) or [])
            original_bcc = list(getattr(message, "bcc", []) or [])

            message.to = redirect_to
            message.cc = redirect_cc
            message.bcc = []

            prefix = (
                "[TEST EMAIL REDIRECT]\n"
                f"Original To: {', '.join(original_to) or '-'}\n"
                f"Original CC: {', '.join(original_cc) or '-'}\n"
                f"Original BCC: {', '.join(original_bcc) or '-'}\n"
                f"DB: ufdxwals_it_test_db\n\n"
            )

            if getattr(message, "subject", "") and not str(message.subject).startswith("[TEST EMAIL]"):
                message.subject = f"[TEST EMAIL] {message.subject}"

            if getattr(message, "body", None):
                if not str(message.body).startswith("[TEST EMAIL REDIRECT]"):
                    message.body = prefix + str(message.body)
            else:
                message.body = prefix

            # If the message has HTML alternatives, prepend a small banner.
            alternatives = getattr(message, "alternatives", None)
            if alternatives:
                new_alternatives = []
                for content, mimetype in alternatives:
                    if mimetype == "text/html" and content and "[TEST EMAIL REDIRECT]" not in content[:200]:
                        banner = (
                            "<div style=\"padding:10px;border:2px dashed #f59e0b;"
                            "background:#fffbeb;color:#92400e;font-family:Arial,sans-serif;"
                            "font-size:12px;margin-bottom:12px;\">"
                            "<strong>[TEST EMAIL REDIRECT]</strong><br>"
                            f"Original To: {', '.join(original_to) or '-'}<br>"
                            f"Original CC: {', '.join(original_cc) or '-'}<br>"
                            f"Original BCC: {', '.join(original_bcc) or '-'}<br>"
                            "DB: ufdxwals_it_test_db"
                            "</div>"
                        )
                        content = banner + content
                    new_alternatives.append((content, mimetype))
                message.alternatives = new_alternatives

        return super().send_messages(email_messages)

