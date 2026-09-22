/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
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
    if (parsed.username || parsed.password || parsed.search || parsed.hash) {
      throw new Error(
        "TOPO_BACKEND_URL must not contain userinfo, query, or fragment",
      )
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
