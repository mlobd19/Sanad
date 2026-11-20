import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const config: NextConfig = {
  // Tout passe par la même adresse (app, API, back-office) : pas de CORS à gérer.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/v/:token", destination: `${backend}/v/:token` },
      { source: "/media/:path*", destination: `${backend}/media/:path*` },
      // Back-office de l'équipe (Django admin) et ses fichiers statiques : une seule adresse pour tout.
      { source: "/admin", destination: `${backend}/admin/` },
      // Les URL de l'admin finissent par « / » : on la conserve, sinon Django redirige en boucle.
      { source: "/admin/:path*/", destination: `${backend}/admin/:path*/` },
      { source: "/admin/:path*", destination: `${backend}/admin/:path*` },
      { source: "/static/:path*", destination: `${backend}/static/:path*` },
    ];
  },
  skipTrailingSlashRedirect: true,
};

export default config;
