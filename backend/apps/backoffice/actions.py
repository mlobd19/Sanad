"""Actions du back-office qui exigent un motif (refus, résiliation…) : page de saisie, puis application."""
from collections.abc import Callable

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _


def changelist_url(opts) -> str:
    return reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")


def reason_page(request, modeladmin, *, objects, title, intro, label, submit, apply: Callable,
                action: str = "", back: str = "", danger: bool = True, done_message: str = ""):
    """Affiche le formulaire de motif ; s'il est envoyé et rempli, applique `apply(obj, motif)` à chaque objet.

    Renvoie None une fois appliqué (l'admin revient alors à la liste), sinon la page du formulaire.
    """
    reason, error = "", ""
    if request.POST.get("sn_confirm"):
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            error = _("Le motif est obligatoire.")
        else:
            done = 0
            for obj in objects:
                try:
                    apply(obj, reason)
                    done += 1
                except ValidationError as exc:
                    modeladmin.message_user(request, f"{obj} : {exc.messages[0]}", messages.ERROR)
            if done:
                modeladmin.message_user(request, done_message % {"n": done} if done_message else _("Fait."),
                                        messages.SUCCESS)
            return None
    context = {
        **modeladmin.admin_site.each_context(request),
        "opts": modeladmin.model._meta,
        "title": title, "intro": intro, "label": label, "submit": submit, "danger": danger,
        "objects": objects, "ids": [obj.pk for obj in objects], "action": action,
        "reason": reason, "error": error, "back": back or changelist_url(modeladmin.model._meta),
    }
    return render(request, "admin/sanad_reason_form.html", context)
