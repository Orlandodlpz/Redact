/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No analytics, no error reporting service, no source map upload. Findings name what
  // is sensitive in someone's image and must not leave the browser except to our API.
  productionBrowserSourceMaps: false,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // Nothing here is cacheable: the page holds the user's image in memory.
          { key: "Cache-Control", value: "no-store" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
