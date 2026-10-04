import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep existing local launchers working while adopting the MedyLink name.
  distDir: (process.env.MEDYLINK_SYNTHETIC ?? process.env.AROGYATRACK_SYNTHETIC) === "true" ? ".next-synthetic" : ".next",
  output: "standalone",
  turbopack: { root: __dirname },
  experimental: { proxyClientMaxBodySize: "24mb" },
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/v1/:path*/` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=()" },
      { key: "Cache-Control", value: "no-store, max-age=0" },
    ] }];
  },
};
export default nextConfig;
