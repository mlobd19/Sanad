import { redirect } from "next/navigation";

/** Ancienne adresse : page commune aux comptes professionnels. */
export default function LegacyForgotPasswordPage() {
  redirect("/connexion/mot-de-passe-oublie");
}
