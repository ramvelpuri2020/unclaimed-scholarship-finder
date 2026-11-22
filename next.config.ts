import path from 'node:path'
import type { NextConfig } from 'next'

/**
 * Next.js app router. Live hunts use arbitrary `/hunt/[id]` ids, so this must
 * run as a Node server rather than a static export.
 */
const nextConfig: NextConfig = {
  images: { unoptimized: true },
  // Pin the workspace root. Without this, Turbopack walks up past the repo
  // (e.g. OneDrive/Desktop/app) and warns about lockfiles it finds there.
  turbopack: { root: path.resolve('.') },
  // Allow the E2B/Blink preview domains to talk to the dev server (Next 16).
  allowedDevOrigins: [
    '*.e2b.dev',
    '*.e2b.app',
    '*.preview-blink.com',
    '*.blink.new',
  ],
}

export default nextConfig
