"""Configure Gmail SMTP without placing an app password in shell history."""
from __future__ import annotations

import argparse
import getpass
import io
import os
from pathlib import Path
import re
import smtplib
import ssl
import stat
import sys
import tempfile
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"
SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


class SetupError(Exception):
    """An actionable error safe to display without server responses or secrets."""


def environment_snapshot(path: Path) -> tuple[bytes, dict[str, str | None]]:
    if not path.is_file() or path.is_symlink():
        raise SetupError("An existing regular backend/.env file is required. Run node scripts/init-env.mjs first; existing secrets will be preserved.")
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise SetupError("python-dotenv is missing. Run this helper with the project's .venv Python after installing backend requirements.") from None
    try:
        content = path.read_bytes()
        values = dotenv_values(stream=io.StringIO(content.decode("utf-8-sig")))
    except (OSError, UnicodeError):
        raise SetupError("Could not read backend/.env as UTF-8. Check its permissions and encoding.") from None
    return content, dict(values)


def gmail_email(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise SetupError("Enter one email address without line breaks.")
    address = value.strip()
    if len(address) > 254 or not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", address):
        raise SetupError("Enter a valid Gmail or Google Workspace email address.")
    return address


def app_password(value: str) -> str:
    password = "".join(value.split())
    if len(password) != 16 or not password.isascii() or not password.isalnum():
        raise SetupError("Enter the 16-character Google app password, not your normal account password. Formatting spaces are removed automatically.")
    return password


def authenticate_smtp(host: str, port: int, username: str, password: str) -> None:
    """Validate credentials over verified STARTTLS. Never sends a message."""
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(username, password)
    except smtplib.SMTPAuthenticationError:
        raise SetupError("SMTP authentication was rejected. For Gmail, enable Google 2-Step Verification and create an app password; your normal password will not work. Check your account's app-password availability.") from None
    except smtplib.SMTPNotSupportedError:
        raise SetupError("The SMTP server does not support the required STARTTLS or authentication. Check the SMTP host and port.") from None
    except ssl.SSLError:
        raise SetupError("The secure SMTP connection could not be verified. Check your computer's clock and trusted certificates.") from None
    except (TimeoutError, OSError):
        raise SetupError("Could not connect to the SMTP server. Check network access, firewall rules, host, and port, then retry.") from None
    except smtplib.SMTPException:
        raise SetupError("The SMTP server could not complete authentication. Retry later or check the provider's SMTP settings.") from None


def check_existing(values: Mapping[str, str | None]) -> None:
    if values.get("EMAIL_BACKEND") != SMTP_BACKEND:
        raise SetupError("The email backend is not configured for SMTP. Run this helper without --check to configure Gmail.")
    host = (values.get("EMAIL_HOST") or "").strip()
    username = values.get("EMAIL_HOST_USER") or ""
    password = values.get("EMAIL_HOST_PASSWORD") or ""
    if not host or any(character.isspace() for character in host) or "://" in host:
        raise SetupError("EMAIL_HOST must contain a valid SMTP hostname without a URL scheme.")
    if not username or "\r" in username or "\n" in username or not password:
        raise SetupError("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set in backend/.env.")
    try:
        port = int(values.get("EMAIL_PORT") or "587")
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SetupError("EMAIL_PORT must be an integer between 1 and 65535.") from None
    if (values.get("EMAIL_USE_TLS") or "").lower() not in {"true", "1", "yes", "on"}:
        raise SetupError("EMAIL_USE_TLS must be true. This helper will not send credentials over an unencrypted connection.")
    authenticate_smtp(host, port, username, password)


def save_settings(path: Path, snapshot: bytes, settings: Mapping[str, str]) -> None:
    """Update only SMTP keys and atomically replace the existing environment file."""
    from dotenv import set_key

    temporary_path: Path | None = None
    try:
        if path.is_symlink() or path.read_bytes() != snapshot:
            raise SetupError("backend/.env changed during setup. Nothing was saved; rerun the helper to preserve those changes.")
        original_mode = stat.S_IMODE(path.stat().st_mode)
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".env.smtp-", suffix=".tmp", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(snapshot)
            temporary.flush()
            os.fsync(temporary.fileno())
        for key, value in settings.items():
            set_key(str(temporary_path), key, value, quote_mode="always", encoding="utf-8")
        with temporary_path.open("r+b") as checked:
            checked.flush()
            os.fsync(checked.fileno())
        temporary_path.chmod(original_mode)
        if path.is_symlink() or path.read_bytes() != snapshot:
            raise SetupError("backend/.env changed during setup. Nothing was saved; rerun the helper to preserve those changes.")
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError:
        raise SetupError("SMTP authentication succeeded, but backend/.env could not be updated. Check file permissions and retry.") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure Gmail SMTP in an existing backend/.env after testing authentication. No email is sent.",
        epilog="Before setup: enable Google 2-Step Verification, then create a Google app password at https://myaccount.google.com/apppasswords. App passwords may be unavailable under some account or organization policies. Enter the app password only at the hidden prompt, never as a command argument. This helper preserves DATABASE_URL and all other environment settings. Restart the backend after saving.",
    )
    parser.add_argument("--check", action="store_true", help="test the existing SMTP credentials without prompting, saving settings, or sending email (requires STARTTLS)")
    arguments = parser.parse_args(argv)
    try:
        snapshot, values = environment_snapshot(ENV_PATH)
        if arguments.check:
            check_existing(values)
            print("SMTP authentication succeeded. No email was sent and no settings were changed.")
            return 0
        if not sys.stdin.isatty():
            raise SetupError("Run this command in an interactive terminal so the app password can be entered at a hidden prompt. Use --check for a noninteractive authentication check.")
        username = gmail_email(input("Gmail / Google Workspace email address: "))
        password = app_password(getpass.getpass("Google app password (hidden): "))
        authenticate_smtp("smtp.gmail.com", 587, username, password)
        save_settings(ENV_PATH, snapshot, {
            "EMAIL_BACKEND": SMTP_BACKEND,
            "EMAIL_HOST": "smtp.gmail.com",
            "EMAIL_PORT": "587",
            "EMAIL_HOST_USER": username,
            "EMAIL_HOST_PASSWORD": password,
            "EMAIL_USE_TLS": "true",
            "DEFAULT_FROM_EMAIL": f"MedyLink <{username}>",
        })
        print("SMTP authentication succeeded and settings were saved in backend/.env. No email was sent. Restart the backend to apply the changes.")
        return 0
    except SetupError as error:
        print(f"SMTP setup: {error}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nSMTP setup cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
