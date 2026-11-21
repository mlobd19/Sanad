"""Plaques enregistrées sous une seule forme (majuscules, sans espaces) : « 6602 BA 00 » → « 6602BA00 »."""
from django.db import migrations


def normalize(apps, schema_editor):
    from apps.policies.models import normalize_plate

    InsuredAsset = apps.get_model("policies", "InsuredAsset")
    for asset in InsuredAsset.objects.all().only("pk", "reference"):
        plate = normalize_plate(asset.reference)
        if plate and plate != asset.reference:
            InsuredAsset.objects.filter(pk=asset.pk).update(reference=plate)


class Migration(migrations.Migration):
    dependencies = [("policies", "0005_declaration_sinistre")]
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
