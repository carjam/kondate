"""Contract step for 0003: drop the unused is_staple column.

0003 removed the field from Django's model state but kept the column so the
previous release could still read it during a deploy overlap. Once 0003 is
live, nothing reads it any more. Deploy this in a release after 0003, never
alongside it.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("kondate", "0005_fix_spellings")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE kondate_ingredient DROP COLUMN is_staple",
                    reverse_sql=(
                        "ALTER TABLE kondate_ingredient "
                        "ADD COLUMN is_staple boolean NOT NULL DEFAULT false"
                    ),
                ),
            ],
        ),
    ]
