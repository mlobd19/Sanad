"use client";

import { useEffect } from "react";

import { useI18n, type Key } from "@/lib/i18n";

/** Validation des champs dans la langue et le style de Sanad, pour tous les formulaires.
 *
 *  Les champs gardent leurs règles HTML (`required`, `type="email"`, `minLength`, `min`/`max`),
 *  mais la bulle du navigateur (langue du système, style du système) est remplacée par un
 *  message sous le champ, traduit, relié au champ (`aria-describedby`, `aria-invalid`).
 *  Monté une fois dans le layout : aucun formulaire n'a besoin de code en plus. */

const ERROR_CLASS = "field-error";
type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

function isControl(el: EventTarget | null): el is Control {
  return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement;
}

/** Message (clé + valeurs) selon la règle non respectée. */
function messageFor(el: Control): [Key, Record<string, string | number>] {
  const v = el.validity;
  if (v.valueMissing) return ["fieldRequired", {}];
  if (v.typeMismatch && el.type === "email") return ["fieldEmail", {}];
  if (v.tooShort && "minLength" in el) return ["fieldTooShort", { n: el.minLength }];
  if ((v.rangeUnderflow || v.rangeOverflow) && el instanceof HTMLInputElement && el.min && el.max) {
    return ["fieldRange", { min: el.min, max: el.max }];
  }
  return ["fieldInvalid", {}];
}

let counter = 0;

export function FormValidation() {
  const { t, lang } = useI18n();

  useEffect(() => {
    let focusedThisRound = false;

    function errorId(el: Control): string {
      if (!el.id) el.id = `champ-${++counter}`;
      return `${el.id}-error`;
    }

    function show(el: Control) {
      const [key, vars] = messageFor(el);
      const id = errorId(el);
      let node = document.getElementById(id);
      if (!node) {
        node = document.createElement("p");
        node.id = id;
        node.className = ERROR_CLASS;
        // Sous le champ ; à la fin du bloc .field (après le préfixe +222 ou l'aide éventuelle).
        (el.closest(".field") ?? el.parentElement)?.appendChild(node);
      }
      node.dataset.key = key;
      node.dataset.vars = JSON.stringify(vars);
      node.textContent = t(key, vars);
      el.setAttribute("aria-invalid", "true");
      const described = (el.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
      if (!described.includes(id)) el.setAttribute("aria-describedby", [...described, id].join(" "));
    }

    function clear(el: Control) {
      if (!el.id) return;
      const id = `${el.id}-error`;
      document.getElementById(id)?.remove();
      el.removeAttribute("aria-invalid");
      const described = (el.getAttribute("aria-describedby") ?? "").split(" ").filter((d) => d && d !== id);
      if (described.length) el.setAttribute("aria-describedby", described.join(" "));
      else el.removeAttribute("aria-describedby");
    }

    function onInvalid(e: Event) {
      if (!isControl(e.target)) return;
      e.preventDefault(); // pas de bulle du navigateur
      show(e.target);
      // Le navigateur signale chaque champ invalide d'un envoi : on place le curseur sur le premier.
      if (!focusedThisRound) {
        focusedThisRound = true;
        e.target.focus();
        // setTimeout et non queueMicrotask : les microtâches passent entre deux événements « invalid ».
        setTimeout(() => { focusedThisRound = false; }, 0);
      }
    }

    function onEdit(e: Event) {
      const el = e.target;
      if (!isControl(el) || !el.id || !document.getElementById(`${el.id}-error`)) return;
      if (el.validity.valid) clear(el);
      else show(el); // le message suit la saisie (ex. « obligatoire » → « email valide »)
    }

    document.addEventListener("invalid", onInvalid, true); // « invalid » ne remonte pas : phase de capture
    document.addEventListener("input", onEdit, true);
    document.addEventListener("change", onEdit, true);
    return () => {
      document.removeEventListener("invalid", onInvalid, true);
      document.removeEventListener("input", onEdit, true);
      document.removeEventListener("change", onEdit, true);
    };
  }, [t]);

  // Changement de langue : les messages déjà affichés sont retraduits.
  useEffect(() => {
    document.querySelectorAll<HTMLElement>(`.${ERROR_CLASS}[data-key]`).forEach((node) => {
      node.textContent = t(node.dataset.key as Key, JSON.parse(node.dataset.vars || "{}"));
    });
  }, [t, lang]);

  return null;
}
