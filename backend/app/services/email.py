from __future__ import annotations

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None
    BotoCoreError = ClientError = Exception

from app.core.config import get_settings


class EmailService:
    def __init__(self):
        self.settings = get_settings()
        has_creds = (
            boto3
            and self.settings.aws_access_key_id
            and self.settings.aws_secret_access_key
            and self.settings.aws_region
        )
        if has_creds:
            self.ses = boto3.client(
                "ses",
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
                region_name=self.settings.aws_region,
            )
        else:
            self.ses = None

    def _send(self, to_email: str, subject: str, html_body: str) -> None:
        from_address = self.settings.email_from_address or "no-reply@aim-platform.test"
        if not self.ses:
            print(
                f"[EMAIL MOCK] {subject} -> {to_email}\n"
                f"Body: {html_body}\n"
            )
            return
        try:
            self.ses.send_email(
                Source=from_address,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Html": {"Data": html_body}},
                },
            )
        except (BotoCoreError, ClientError) as exc:
            print(f"[EMAIL] Failed to send email to {to_email}: {exc}")
            raise

    def send_verification_email(self, email: str, token: str) -> None:
        frontend = self.settings.frontend_base_url.rstrip("/")
        link = f"{frontend}/auth/verify?token={token}"
        html_body = (
            "<p>Thanks for joining AIM. Click the link below to verify your account:</p>"
            f'<p><a href="{link}">{link}</a></p>'
        )
        self._send(email, "Confirm your AIM account", html_body)

    def send_password_reset_email(self, email: str, token: str) -> None:
        frontend = self.settings.frontend_base_url.rstrip("/")
        link = f"{frontend}/auth/reset-password?token={token}"
        html_body = (
            "<p>We received a request to reset your password. If this was you, click the link below:</p>"
            f'<p><a href="{link}">Reset password</a></p>'
            "<p>If you didn't request this, you can ignore this email.</p>"
        )
        self._send(email, "Reset your AIM password", html_body)
