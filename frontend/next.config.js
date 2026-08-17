const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${baseUrl}/api/:path*` }];
  }
};
module.exports = nextConfig;
