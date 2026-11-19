import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const config: NextConfig = {
  // L'app parle au backend Django via le même domaine : pas de CORS à gérer.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/v/:token", destination: `${backend}/v/:token` },
    ];
  },
  skipTrailingSlashRedirect: true,
};

export default config;
