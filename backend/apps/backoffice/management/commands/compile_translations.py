"""Traductions du back-office sans les outils gettext du système.

    python manage.py compile_translations           # locale/ar/.../django.po → django.mo
    python manage.py compile_translations --missing # textes du code sans traduction arabe

Le français est la langue des sources : seuls les textes arabes sont à fournir.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PO = Path(settings.BASE_DIR) / "locale" / "ar" / "LC_MESSAGES" / "django.po"

# Appels Python : une ou plusieurs chaînes concaténées implicitement (« "a" "b" » = "ab").
PY_CALL = re.compile(r'(?<![\w.])(?:_|gettext|gettext_lazy)\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)[,)]', re.S)
PY_PART = re.compile(r'"((?:[^"\\]|\\.)*)"')
PATTERNS = [
    re.compile(r'\{%\s*translate\s+"([^"]*)"'),
    re.compile(r"\{%\s*translate\s+'([^']*)'"),
    re.compile(r"\{%\s*blocktranslate(?:\s+with[^%]*)?\s*%\}(.*?)\{%\s*endblocktranslate\s*%\}", re.S),
]


def source_messages() -> set[str]:
    """Textes marqués à traduire dans le code Python et les gabarits du projet."""
    root = Path(settings.BASE_DIR) / "apps"
    found = set()
    for path in list(root.rglob("*.py")) + list(root.rglob("*.html")):
        if "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for call in PY_CALL.findall(text):
            found.add("".join(PY_PART.findall(call)).replace('\\"', '"'))
        for pattern in PATTERNS:
            for match in pattern.findall(text):
                msg = match
                if pattern.pattern.startswith(r"\{%\s*blocktranslate"):
                    msg = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"%(\1)s", msg)
                found.add(msg)
    return found


class Command(BaseCommand):
    help = "Compile les traductions arabes (locale/ar) et signale les textes non traduits."

    def add_arguments(self, parser):
        parser.add_argument("--missing", action="store_true", help="Lister les textes sans traduction arabe.")

    def handle(self, *args, missing=False, **options):
        try:
            import polib
        except ImportError as exc:  # dépendance de développement
            raise CommandError("pip install -r requirements-dev.txt (polib)") from exc
        po = polib.pofile(str(PO))
        translated = {e.msgid for e in po if e.msgstr}
        todo = sorted(source_messages() - translated)
        if missing:
            for msg in todo:
                self.stdout.write(msg)
            self.stdout.write(f"{len(todo)} texte(s) sans traduction.")
            return
        po.save_as_mofile(str(PO.with_suffix(".mo")))
        self.stdout.write(self.style.SUCCESS(f"{len(translated)} traduction(s) compilée(s)."))
        if todo:
            self.stdout.write(self.style.WARNING(f"{len(todo)} texte(s) sans traduction : --missing pour la liste."))
