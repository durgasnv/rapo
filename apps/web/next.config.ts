import type { NextConfig } from "next";

const apiOrigin = new URL(
  process.env.RAPO_API_ORIGIN ?? "http://localhost:8000",
);
if (
  apiOrigin.username ||
  apiOrigin.password ||
  apiOrigin.search ||
  apiOrigin.hash ||
  apiOrigin.pathname !== "/" ||
  !["http:", "https:"].includes(apiOrigin.protocol) ||
  (apiOrigin.protocol === "http:" &&
    !["localhost", "127.0.0.1", "[::1]"].includes(apiOrigin.hostname))
) {
  throw new Error(
    "RAPO_API_ORIGIN must be an HTTPS origin or a local HTTP origin.",
  );
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiOrigin.origin}/:path*` },
    ];
  },
};

export default nextConfig;
