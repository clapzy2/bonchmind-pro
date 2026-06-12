import type { NextConfig } from "next";

const backendUrl = process.env.BONCHMIND_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone/server.js) so the
  // production Docker image can run on a slim node base without node_modules.
  // Does not affect `next dev`.
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
