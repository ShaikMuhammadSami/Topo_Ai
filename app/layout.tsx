import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import { Geist, Geist_Mono, Roboto_Slab } from 'next/font/google'
import './globals.css'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})
const robotoSlab = Roboto_Slab({
  variable: '--font-slab',
  subsets: ['latin'],
  weight: ['700', '800', '900'],
})

export const metadata: Metadata = {
  title: 'topo ai - evidence-based RCA for kubernetes',
  description:
    'topo ai correlates your temporal k8s graph, git diffs, deploy events and live signals into a ranked list of hypotheses - each with supporting evidence and a confidence you can defend in review.',
  icons: {
    icon: [
      {
        url: '/t.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/t.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/svg.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/t.png',
  },
}

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#0a0a0a',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`dark bg-background ${geistSans.variable} ${geistMono.variable} ${robotoSlab.variable}`}
    >
      <body className="font-sans antialiased">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
