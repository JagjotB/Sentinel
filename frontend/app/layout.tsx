import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] });
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000';

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: 'Sentinel · Deep-Agent Reliability Engineering',
  description:
    'Evidence-backed, policy-gated incident investigation with deep-agent orchestration.',
  openGraph: {
    title: 'SENTINEL',
    description: 'Deep-Agent Reliability Engineering',
    images: [
      {
        url: '/og.png',
        width: 1536,
        height: 1024,
        alt: 'Sentinel reliability engineering evidence graph',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'SENTINEL',
    description: 'Deep-Agent Reliability Engineering',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
