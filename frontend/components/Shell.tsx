"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { api, getToken, type User } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

import { Icon } from "./Icon";

/** Charge l'utilisateur connecté ; renvoie vers /connexion sinon. */
export function useUser() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    if (!getToken()) {
      router.replace("/connexion");
      return;
    }
    api<User>("me").then(setUser).catch(() => router.replace("/connexion"));
  }, [router]);
  return { user, setUser };
}

export function TopBar({ title, back }: { title: string; back?: string }) {
  const { t } = useI18n();
  return (
    <header className="topbar">
      {back && (
        <Link href={back} className="iconbtn" aria-label={t("back")}>
          <Icon name="back" strokeWidth={2} />
        </Link>
      )}
      <h1>{title}</h1>
    </header>
  );
}

export function BottomNav() {
  const { t } = useI18n();
  const path = usePathname();
  const items = [
    { href: "/", label: t("navHome"), icon: "home" },
    { href: "/contrats", label: t("navContracts"), icon: "file" },
    { href: "/profil", label: t("navProfile"), icon: "user" },
  ];
  return (
    <nav className="bottomnav" aria-label="Navigation principale">
      {items.map((item) => {
        const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
        return (
          <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
            <Icon name={item.icon} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Loading() {
  const { t } = useI18n();
  return (
    <div className="center" role="status">
      <div className="spinner" />
      <span className="muted">{t("loading")}</span>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div className="banner red" role="alert">
      <span className="grow">{message || t("error")}</span>
      {onRetry && (
        <button type="button" className="btn outline" onClick={onRetry}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}

export function Steps({ n, total = 5 }: { n: number; total?: number }) {
  const { t } = useI18n();
  return (
    <div className="stack" style={{ gap: 6 }}>
      <span className="small muted">{t("step", { n, total })}</span>
      <div className="progress" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <div key={i} className={i < n ? "done" : ""} />
        ))}
      </div>
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const { t } = useI18n();
  const tone = status === "active" ? "" : status === "paid" || status === "draft" ? "warn" : status === "refused" ? "bad" : "quiet";
  return <span className={`pill ${tone}`}>{t(`status_${status}` as Parameters<typeof t>[0])}</span>;
}

export function App({ children }: { children: ReactNode }) {
  return <div className="app">{children}</div>;
}
