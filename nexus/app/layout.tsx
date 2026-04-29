import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Nexus — Business Operating System',
  description: 'CRM, HR og Marketing platform til moderne virksomheder',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 rx=%2220%22 fill=%22%234f46e5%22/><path d=%22M25 75 L75 25 M25 25 L50 50 L75 75%22 stroke=%22white%22 stroke-width=%2212%22 stroke-linecap=%22round%22 fill=%22none%22/></svg>',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="da" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  )
}
