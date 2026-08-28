/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const backendUrl = (
      process.env.TOPO_BACKEND_URL ?? "http://127.0.0.1:8000"
    ).replace(/\/$/, "")
    const parsed = new URL(backendUrl)
    if (!["http:", "https:"].includes(parsed.protocol)) {
      throw new Error("TOPO_BACKEND_URL must use http or https")
    }
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
