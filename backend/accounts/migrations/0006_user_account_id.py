import secrets

from django.db import migrations, models

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PREFIXES = {"patient": "P", "doctor": "D", "pharmacist": "PH", "admin": "A"}


def populate_account_ids(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    users = User.objects.using(schema_editor.connection.alias)
    used = set(
        users.exclude(account_id__isnull=True)
        .exclude(account_id="")
        .values_list("account_id", flat=True)
    )
    for user in users.filter(account_id__isnull=True).only("id", "role").iterator():
        for _ in range(100):
            suffix = "".join(secrets.choice(ALPHABET) for _ in range(6))
            candidate = f"{PREFIXES[user.role]}-{suffix}"
            if candidate not in used:
                break
        else:
            raise RuntimeError("Unable to allocate a unique account ID.")
        users.filter(pk=user.pk).update(account_id=candidate)
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_remove_authenticator"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="account_id",
            field=models.CharField(max_length=9, null=True, editable=False),
        ),
        migrations.RunPython(populate_account_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="account_id",
            field=models.CharField(max_length=9, unique=True, editable=False),
        ),
    ]
