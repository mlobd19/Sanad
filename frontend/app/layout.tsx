import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { DemoBanner } from "@/components/DemoBanner";
import { I18nProvider } from "@/lib/i18n";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sanad",
  description: "Toutes vos assurances, un seul espace.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  appleWebApp: { capable: true, title: "Sanad", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0b6e4f" },
    { media: "(prefers-color-scheme: dark)", color: "#05241a" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // data-theme est posé par le script ci-dessous avant l'hydratation : écart attendu entre serveur et client.
    <html lang="fr" dir="ltr" suppressHydrationWarning>
      <head>
        {/* Applique le choix d'apparence enregistré avant le premier affichage (pas d'éclair blanc). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=Noto+Kufi+Arabic:wght@400;600;700&display=swap"
        />
      </head>
      <body>
        <I18nProvider>
          <DemoBanner />
          {children}
        </I18nProvider>
      </body>
    </html>
  );
}
