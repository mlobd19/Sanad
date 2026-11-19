"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "fr" | "ar";

const fr = {
  appName: "Sanad",
  tagline: "Toutes vos assurances, un seul espace.",
  // Connexion
  loginTitle: "Connexion",
  loginIntro: "Entrez votre numéro mauritanien. Vous recevrez un code par SMS.",
  phoneLabel: "Numéro de téléphone",
  phonePlaceholder: "36 00 00 00",
  sendCode: "Recevoir le code",
  codeLabel: "Code reçu par SMS",
  codeSentTo: "Code envoyé au {phone}.",
  verify: "Se connecter",
  changeNumber: "Changer de numéro",
  resend: "Renvoyer le code",
  // Accueil
  hello: "Bonjour",
  helloName: "Bonjour, {name}",
  myContracts: "Mes contrats",
  noContracts: "Aucun contrat pour l'instant. Assurez votre véhicule en quelques minutes.",
  subscribe: "Souscrire une assurance",
  available: "Disponible",
  soon: "Bientôt",
  auto: "Auto",
  health: "Santé",
  home: "Habitation",
  travel: "Voyage",
  takaful: "Takaful",
  pro: "Pro & cyber",
  renewTitle: "Votre assurance auto expire dans {days} jour(s)",
  renewText: "Renouvelez sans rien ressaisir.",
  renew: "Renouveler",
  seeAttestation: "Voir l'attestation",
  seeDetails: "Voir le détail",
  expiresOn: "Échéance : {date}",
  premiumPerYear: "{amount} / an",
  // Navigation
  navHome: "Accueil",
  navContracts: "Contrats",
  navProfile: "Profil",
  back: "Retour",
  // Véhicule
  vehicleTitle: "Votre véhicule",
  plate: "Immatriculation",
  plateHint: "Telle qu'écrite sur la carte grise.",
  make: "Marque et modèle (facultatif)",
  fiscalPower: "Puissance fiscale (CV)",
  usage: "Usage",
  usagePersonal: "Personnel",
  usageCommercial: "Commercial",
  usageTaxi: "Taxi",
  myVehicles: "Mes véhicules",
  addVehicle: "Ajouter un véhicule",
  seeQuotes: "Voir les offres",
  // Devis
  quotesTitle: "Choisir une offre",
  quotesCount: "{count} offres pour 12 mois",
  step: "Étape {n} sur {total}",
  choose: "Choisir",
  selected: "Sélectionnée",
  continueToPay: "Continuer vers le paiement",
  startsOn: "Date d'effet",
  noQuotes: "Aucune offre disponible pour ce véhicule pour le moment.",
  // Paiement
  payTitle: "Paiement",
  summary: "Récapitulatif",
  offer: "Offre",
  vehicle: "Véhicule",
  period: "Période",
  twelveMonths: "12 mois",
  total: "Total à payer",
  method: "Moyen de paiement",
  payerPhone: "Numéro du compte à débiter",
  payHint: "Vous confirmerez le paiement dans votre application mobile money.",
  pay: "Payer {amount}",
  waitingConfirm: "En attente de votre confirmation dans l'application de paiement…",
  simulate: "Simuler la confirmation (développement)",
  waitingInsurer: "Paiement confirmé. L'assureur valide votre contrat ; vous recevrez l'attestation sur WhatsApp.",
  // Contrat / attestation
  contractTitle: "Mon contrat",
  paymentConfirmed: "Paiement confirmé · contrat actif",
  attestationTitle: "Attestation d'assurance automobile",
  insured: "Assuré",
  insurer: "Assureur",
  cover: "Garantie",
  validFrom: "Valable du",
  validTo: "au",
  signed: "Signée numériquement",
  signedText: "À présenter lors d'un contrôle. L'agent scanne le QR code et vérifie l'attestation, même sans réseau.",
  downloadQr: "Télécharger",
  share: "Partager",
  openCheck: "Voir ce que voit l'agent de contrôle",
  refusedText: "L'assureur n'a pas validé ce contrat ({reason}). Vous avez été remboursé.",
  // Profil
  profileTitle: "Mon profil",
  fullName: "Nom complet",
  nni: "NNI",
  language: "Langue",
  save: "Enregistrer",
  saved: "Enregistré.",
  logout: "Se déconnecter",
  kyc: "Vérification d'identité",
  kyc_none: "Non commencée",
  kyc_pending: "En cours",
  kyc_verified: "Vérifiée",
  kyc_rejected: "Refusée",
  // Divers
  loading: "Chargement…",
  error: "Une erreur est survenue.",
  retry: "Réessayer",
  status_draft: "En attente de paiement",
  status_paid: "En validation",
  status_active: "Active",
  status_refused: "Refusée",
  status_cancelled: "Résiliée",
  status_expired: "Expirée",
};

export type Key = keyof typeof fr;

const ar: Record<Key, string> = {
  appName: "سند",
  tagline: "كل تأميناتك في مكان واحد.",
  loginTitle: "تسجيل الدخول",
  loginIntro: "أدخل رقمك الموريتاني. ستصلك رسالة نصية برمز.",
  phoneLabel: "رقم الهاتف",
  phonePlaceholder: "36 00 00 00",
  sendCode: "استلام الرمز",
  codeLabel: "الرمز المستلم",
  codeSentTo: "تم إرسال الرمز إلى {phone}.",
  verify: "دخول",
  changeNumber: "تغيير الرقم",
  resend: "إعادة إرسال الرمز",
  hello: "مرحبا",
  helloName: "مرحبا، {name}",
  myContracts: "عقودي",
  noContracts: "لا توجد عقود بعد. أمّن سيارتك في دقائق.",
  subscribe: "اشترك في تأمين",
  available: "متاح",
  soon: "قريبا",
  auto: "السيارات",
  health: "الصحة",
  home: "المسكن",
  travel: "السفر",
  takaful: "التكافل",
  pro: "المهنيون والسيبراني",
  renewTitle: "ينتهي تأمين سيارتك خلال {days} يوم",
  renewText: "جدّده دون إعادة إدخال بياناتك.",
  renew: "تجديد",
  seeAttestation: "عرض الشهادة",
  seeDetails: "عرض التفاصيل",
  expiresOn: "تاريخ الانتهاء: {date}",
  premiumPerYear: "{amount} / سنة",
  navHome: "الرئيسية",
  navContracts: "العقود",
  navProfile: "حسابي",
  back: "رجوع",
  vehicleTitle: "سيارتك",
  plate: "رقم اللوحة",
  plateHint: "كما هو مكتوب في البطاقة الرمادية.",
  make: "الماركة والطراز (اختياري)",
  fiscalPower: "القوة الجبائية (حصان)",
  usage: "الاستعمال",
  usagePersonal: "شخصي",
  usageCommercial: "تجاري",
  usageTaxi: "أجرة",
  myVehicles: "سياراتي",
  addVehicle: "إضافة سيارة",
  seeQuotes: "عرض العروض",
  quotesTitle: "اختر عرضا",
  quotesCount: "{count} عروض لمدة 12 شهرا",
  step: "الخطوة {n} من {total}",
  choose: "اختيار",
  selected: "مختار",
  continueToPay: "المتابعة إلى الدفع",
  startsOn: "تاريخ السريان",
  noQuotes: "لا توجد عروض متاحة لهذه السيارة حاليا.",
  payTitle: "الدفع",
  summary: "الملخص",
  offer: "العرض",
  vehicle: "السيارة",
  period: "المدة",
  twelveMonths: "12 شهرا",
  total: "المبلغ الإجمالي",
  method: "وسيلة الدفع",
  payerPhone: "رقم الحساب المراد خصمه",
  payHint: "ستؤكد الدفع في تطبيق الدفع عبر الهاتف.",
  pay: "ادفع {amount}",
  waitingConfirm: "في انتظار تأكيدك في تطبيق الدفع…",
  simulate: "محاكاة التأكيد (للتطوير)",
  waitingInsurer: "تم تأكيد الدفع. شركة التأمين تراجع عقدك، وستصلك الشهادة عبر واتساب.",
  contractTitle: "عقدي",
  paymentConfirmed: "تم تأكيد الدفع · العقد ساري",
  attestationTitle: "شهادة تأمين السيارة",
  insured: "المؤمَّن له",
  insurer: "شركة التأمين",
  cover: "الضمان",
  validFrom: "سارية من",
  validTo: "إلى",
  signed: "موقّعة رقميا",
  signedText: "تُقدَّم عند المراقبة. يمسح العون رمز QR ويتحقق من الشهادة حتى دون اتصال.",
  downloadQr: "تنزيل",
  share: "مشاركة",
  openCheck: "ما يراه عون المراقبة",
  refusedText: "لم توافق شركة التأمين على هذا العقد ({reason}). تم رد المبلغ.",
  profileTitle: "حسابي",
  fullName: "الاسم الكامل",
  nni: "الرقم الوطني",
  language: "اللغة",
  save: "حفظ",
  saved: "تم الحفظ.",
  logout: "تسجيل الخروج",
  kyc: "التحقق من الهوية",
  kyc_none: "لم يبدأ",
  kyc_pending: "قيد التحقق",
  kyc_verified: "تم التحقق",
  kyc_rejected: "مرفوض",
  loading: "جار التحميل…",
  error: "حدث خطأ.",
  retry: "إعادة المحاولة",
  status_draft: "في انتظار الدفع",
  status_paid: "قيد المراجعة",
  status_active: "ساري",
  status_refused: "مرفوض",
  status_cancelled: "ملغى",
  status_expired: "منتهي",
};

const dictionaries: Record<Lang, Record<Key, string>> = { fr, ar };
const LANG_KEY = "sanad.lang";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: Key, vars?: Record<string, string | number>) => string };

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("fr");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(LANG_KEY);
      if (saved === "ar" || saved === "fr") setLangState(saved);
    } catch {
      /* rien */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      /* rien */
    }
  }, []);

  const t = useCallback(
    (key: Key, vars?: Record<string, string | number>) => {
      let text = dictionaries[lang][key] ?? fr[key];
      for (const [k, v] of Object.entries(vars ?? {})) text = text.replace(`{${k}}`, String(v));
      return text;
    },
    [lang],
  );

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n hors de I18nProvider");
  return ctx;
}
