import type { NextConfig } from "next";

const apiInternalUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactCompiler: true,
  typedRoutes: true,
  output: "standalone",
  // The browser talks to FastAPI through the Next.js origin so the session cookie
  // stays first-party and no CORS configuration is needed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiInternalUrl}/api/:path*` }];
  },
};

export default nextConfig;
