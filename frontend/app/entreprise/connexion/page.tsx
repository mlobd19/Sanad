import { redirect } from "next/navigation";

/** Ancienne adresse : la connexion professionnelle est sur la page unique /connexion. */
export default function LegacyLoginPage() {
  redirect("/connexion?espace=pro");
}
