"""Label the database without changing identities or historical clinical records."""
from django.db import migrations


LABEL = "MedyLink healthcare application database."


def label_database(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()")
        database, previous = cursor.fetchone()
        # Preserve an operator's existing description, changing only the brand.
        label = LABEL if previous is None else previous.replace("ArogyaTrack", "MedyLink").replace("AROGYATRACK", "MEDYLINK").replace("arogyatrack", "medylink")
        if label != previous:
            cursor.execute(f"COMMENT ON DATABASE {connection.ops.quote_name(database)} IS %s", [label])


def restore_label(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()")
        database, current = cursor.fetchone()
        label = None if current == LABEL else (current.replace("MedyLink", "ArogyaTrack").replace("MEDYLINK", "AROGYATRACK").replace("medylink", "arogyatrack") if current else current)
        if label != current:
            cursor.execute(f"COMMENT ON DATABASE {connection.ops.quote_name(database)} IS %s", [label])


class Migration(migrations.Migration):
    dependencies = [("analytics", "0002_mlrun")]
    operations = [migrations.RunPython(label_database, restore_label)]
