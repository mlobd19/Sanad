"""Vérification par identité numérique (eID Houwiyeti) : plus aucune pièce d'identité.

Supprime les pièces déjà déposées (fichiers privés compris), remet à « non vérifiée »
les comptes en attente ou refusés sur pièce, et convertit le journal des vérifications.
"""
from pathlib import Path

from django.db import migrations, models

OUTCOMES = {"match": "valid", "mismatch": "no_eid"}  # not_found (NNI introuvable) garde sa valeur


def delete_identity_documents(apps, schema_editor):
    KycDocument = apps.get_model("accounts", "KycDocument")
    for doc in KycDocument.objects.all().iterator():
        if doc.file:
            folder = None
            try:
                folder = Path(doc.file.path).parent
            except (NotImplementedError, ValueError):
                pass
            doc.file.delete(save=False)
            if folder is not None and folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()  # dossier kyc/<compte> vide
        doc.delete()


def convert(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    IdentityCheck = apps.get_model("accounts", "IdentityCheck")
    User.objects.filter(kyc_status__in=["pending", "rejected"]).update(kyc_status="none")
    for old, new in OUTCOMES.items():
        IdentityCheck.objects.filter(outcome=old).update(outcome=new)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_jetons_et_totp"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="full_name_ar",
            field=models.CharField(blank=True, max_length=120, verbose_name="nom en arabe"),
        ),
        migrations.AlterField(
            model_name="identitycheck",
            name="outcome",
            field=models.CharField(max_length=16, verbose_name="résultat"),
        ),
        migrations.RunPython(delete_identity_documents, migrations.RunPython.noop),
        migrations.RunPython(convert, migrations.RunPython.noop),
    ]
