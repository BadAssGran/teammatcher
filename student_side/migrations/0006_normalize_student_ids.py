from django.db import migrations


def normalize_student_ids(apps, schema_editor):
    StudentProfile = apps.get_model("student_side", "StudentProfile")

    # 1. Look for IDs that would clash after normalizing. Do NOT delete anything.
    first_seen = {}
    clashes = []
    for profile in StudentProfile.objects.all():
        clean_id = (profile.student_id or "").strip().lower()  # same rule as models.py
        if clean_id in first_seen:
            clashes.append(f"{clean_id!r}: profiles {first_seen[clean_id]} and {profile.pk}")
        else:
            first_seen[clean_id] = profile.pk
    if clashes:
        raise RuntimeError(
            "Duplicate student IDs found, nothing was changed. "
            "Agree with the team how to fix them first: " + "; ".join(clashes)
        )

    # 2. No clashes: save every ID in its normalized form.
    for profile in StudentProfile.objects.all():
        clean_id = (profile.student_id or "").strip().lower()
        if profile.student_id != clean_id:
            profile.student_id = clean_id
            profile.save(update_fields=["student_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("student_side", "0005_setupcode_learnercredential"),
    ]

    operations = [
        migrations.RunPython(normalize_student_ids, migrations.RunPython.noop),
    ]
