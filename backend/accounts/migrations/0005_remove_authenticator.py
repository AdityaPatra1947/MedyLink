from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_emailverificationchallenge"),
    ]

    # Authenticator enrollment and its stored secrets are intentionally retired.
    # Account credentials, verified emails, sessions and security audit remain.
    operations = [
        migrations.RemoveField(model_name="authsession", name="mfa_verified"),
        migrations.RemoveField(model_name="user", name="last_totp_counter"),
        migrations.RemoveField(model_name="user", name="mfa_secret"),
        migrations.DeleteModel(name="MFAChallenge"),
        migrations.DeleteModel(name="RecoveryCode"),
    ]
