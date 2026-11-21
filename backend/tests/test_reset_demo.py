"""Commande reset_demo : efface les données et recrée la démo, jamais hors DEMO_MODE."""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.accounts.models import User
from apps.catalog.models import Insurer


@pytest.fixture
def logos(tmp_path):
    folder = tmp_path / "logos"
    folder.mkdir()
    Image.new("RGB", (8, 8), "green").save(folder / "nasr.png")
    return folder


@pytest.mark.django_db(transaction=True)
def test_reset_demo_efface_et_recree(settings, logos):
    settings.DEMO_MODE, settings.DEMO_PASSWORD = True, "Mot-de-passe-demo-2026"
    call_command("seed_demo", verbosity=0)
    User.objects.create_user(phone="+22236000000", full_name="Client de test")
    piece = settings.PRIVATE_MEDIA_ROOT / "kyc" / "piece.jpg"
    piece.parent.mkdir(parents=True)
    piece.write_bytes(b"x")

    call_command("reset_demo", yes=True, logos=str(logos), stdout=io.StringIO())

    assert not User.objects.filter(phone="+22236000000").exists()
    assert not piece.exists() and settings.PRIVATE_MEDIA_ROOT.is_dir()
    assert Insurer.objects.count() == 4
    assert User.objects.filter(role=User.Role.INSURER_AGENT).count() == 4
    assert Insurer.objects.get(slug="nasr").logo


@pytest.mark.django_db
def test_reset_demo_refuse_hors_demo_mode(settings):
    settings.DEMO_MODE = False
    settings.DEBUG = True  # DEBUG seul ne suffit pas
    call_command("seed_demo", verbosity=0)
    with pytest.raises(CommandError):
        call_command("reset_demo", yes=True)
    assert Insurer.objects.count() == 4


@pytest.mark.django_db
def test_reset_demo_annule_sans_oui(settings, monkeypatch):
    settings.DEMO_MODE = True
    call_command("seed_demo", verbosity=0)
    monkeypatch.setattr("builtins.input", lambda _: "non")
    with pytest.raises(CommandError):
        call_command("reset_demo")
    assert Insurer.objects.count() == 4
