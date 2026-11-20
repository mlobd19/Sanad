"""Envoi de messages (SMS, WhatsApp, e-mail) derrière une interface unique.

Le backend réel (agrégateur SMS local, fournisseur WhatsApp Business) se
branche via NOTIFICATION_BACKEND sans toucher au code métier.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.utils.module_loading import import_string

TEMPLATES = {
    "otp": {
        "fr": "Votre code {platform} : {code}. Il expire dans {minutes} minutes. Ne le partagez avec personne.",
        "ar": "رمزك في {platform}: {code}. ينتهي خلال {minutes} دقائق. لا تشاركه مع أحد.",
    },
    "attestation_issued": {
        "fr": "Votre attestation d'assurance n° {number} est prête : {url}",
        "ar": "شهادة التأمين رقم {number} جاهزة: {url}",
    },
    "policy_refused": {
        "fr": "L'assureur n'a pas pu valider votre demande. Vous êtes remboursé de {amount} MRU.",
        "ar": "لم تتمكن شركة التأمين من قبول طلبك. سيتم رد مبلغ {amount} أوقية.",
    },
    "renewal_reminder": {
        "fr": "Votre assurance auto ({plate}) expire dans {days} jour(s). Renouvelez-la sur {platform}.",
        "ar": "ينتهي تأمين سيارتك ({plate}) خلال {days} يوم. جدده على {platform}.",
    },
    # E-mails (comptes professionnels)
    "password_invite": {
        "fr": (
            "Bonjour {name},\n\n"
            "Un compte {platform} a été ouvert pour vous ({role}).\n"
            "Choisissez votre mot de passe avec ce lien, valable 72 heures :\n{link}\n\n"
            "À chaque connexion, vous saisirez votre email, ce mot de passe, puis un code reçu par SMS "
            "au {phone}.\n\nSi vous n'attendiez pas ce message, ignorez-le."
        ),
        "ar": (
            "مرحبا {name}،\n\n"
            "تم فتح حساب لك في {platform} ({role}).\n"
            "اختر كلمة المرور عبر هذا الرابط، الصالح لمدة 72 ساعة:\n{link}\n\n"
            "عند كل دخول، ستدخل بريدك الإلكتروني وكلمة المرور ثم رمزا يصلك برسالة نصية على {phone}.\n\n"
            "إذا لم تكن تنتظر هذه الرسالة، فتجاهلها."
        ),
    },
    "password_reset": {
        "fr": (
            "Bonjour {name},\n\n"
            "Pour choisir un nouveau mot de passe {platform}, ouvrez ce lien, valable 72 heures :\n{link}\n\n"
            "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe actuel reste valable."
        ),
        "ar": (
            "مرحبا {name}،\n\n"
            "لاختيار كلمة مرور جديدة في {platform}، افتح هذا الرابط الصالح لمدة 72 ساعة:\n{link}\n\n"
            "إذا لم تطلب ذلك، فتجاهل هذه الرسالة: كلمة المرور الحالية تبقى صالحة."
        ),
    },
    "company_verified": {
        "fr": (
            "Bonjour,\n\nL'entreprise {company} est vérifiée sur {platform}. Vous pouvez désormais payer "
            "vos contrats et recevoir vos attestations.\n"
        ),
        "ar": "مرحبا،\n\nتم التحقق من الشركة {company} على {platform}. يمكنكم الآن دفع عقودكم واستلام شهاداتكم.\n",
    },
    "company_rejected": {
        "fr": (
            "Bonjour,\n\nNous n'avons pas pu vérifier l'entreprise {company} sur {platform}.\n"
            "Motif : {reason}\n\nDéposez une pièce corrigée depuis l'onglet « Entreprise » : "
            "la vérification reprendra.\n"
        ),
        "ar": (
            "مرحبا،\n\nلم نتمكن من التحقق من الشركة {company} على {platform}.\nالسبب: {reason}\n\n"
            "أودعوا وثيقة مصححة من تبويب «الشركة» لاستئناف التحقق.\n"
        ),
    },
}

SUBJECTS = {
    "company_verified": {"fr": "{platform} : entreprise vérifiée", "ar": "{platform}: تم التحقق من الشركة"},
    "company_rejected": {"fr": "{platform} : vérification de l'entreprise refusée", "ar": "{platform}: رُفض التحقق من الشركة"},
    "password_invite": {"fr": "Votre compte {platform} : choisissez votre mot de passe", "ar": "حسابك في {platform}: اختر كلمة المرور"},
    "password_reset": {"fr": "{platform} : nouveau mot de passe", "ar": "{platform}: كلمة مرور جديدة"},
}


def render(template: str, language: str, context: dict) -> str:
    variants = TEMPLATES[template]
    text = variants.get(language) or variants["fr"]
    return text.format(platform=settings.PLATFORM_NAME, **context)


def notify(channel: str, to: str, template: str, context: dict, language: str = "fr"):
    body = render(template, language, context)
    if channel == "email":
        # Les e-mails passent par le système d'envoi de Django (console en dev, SMTP en production).
        subjects = SUBJECTS[template]
        subject = (subjects.get(language) or subjects["fr"]).format(platform=settings.PLATFORM_NAME)
        return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to]) == 1
    backend = import_string(settings.NOTIFICATION_BACKEND)()
    return backend.send(channel=channel, to=to, body=body)
