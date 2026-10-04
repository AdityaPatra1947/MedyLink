import secrets

ACCOUNT_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ACCOUNT_ID_PREFIXES = {
    "patient": "P",
    "doctor": "D",
    "pharmacist": "PH",
    "admin": "A",
}


def generate_account_id(role):
    prefix = ACCOUNT_ID_PREFIXES[role]
    suffix = "".join(secrets.choice(ACCOUNT_ID_ALPHABET) for _ in range(6))
    return f"{prefix}-{suffix}"
