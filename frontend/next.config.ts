import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_BUILD_DIR ?? '.next',
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*/',
        destination: `${process.env.DHCP_TOOL_API_URL ?? 'http://127.0.0.1:8000'}/api/v1/:path*/`,
      },
    ];
  },
};

export default nextConfig;
