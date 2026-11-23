"""Deux usages seulement : tout véhicule et tout devis « taxi » passent en « commercial ».

Les polices déjà émises gardent leur montant : seule la description de l'usage change,
la prime enregistrée (Policy.premium, Quote.premium) n'est jamais recalculée.
Le facteur tarifaire « usage = taxi » disparaît du catalogue.
"""
from django.db import migrations


def taxi_to_commercial(apps, schema_editor):
    InsuredAsset = apps.get_model("policies", "InsuredAsset")
    Quote = apps.get_model("policies", "Quote")
    TariffFactor = apps.get_model("catalog", "TariffFactor")

    for asset in InsuredAsset.objects.all().only("pk", "attributes"):
        if (asset.attributes or {}).get("usage") == "taxi":
            InsuredAsset.objects.filter(pk=asset.pk).update(attributes={**asset.attributes, "usage": "commercial"})
    for quote in Quote.objects.all().only("pk", "attributes_snapshot"):
        if (quote.attributes_snapshot or {}).get("usage") == "taxi":
            Quote.objects.filter(pk=quote.pk).update(
                attributes_snapshot={**quote.attributes_snapshot, "usage": "commercial"})
    TariffFactor.objects.filter(attribute="usage", equals="taxi").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("policies", "0006_plaques_normalisees"),
        ("catalog", "0005_duree_portee_par_le_devis"),
    ]
    operations = [migrations.RunPython(taxi_to_commercial, migrations.RunPython.noop)]
