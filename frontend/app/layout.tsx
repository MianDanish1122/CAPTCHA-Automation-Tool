import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: 'CAPTCHA Inspector — Technology Brainz',
  description:
    'Enterprise-grade CAPTCHA detection, smart contact crawler, synthetic OCR benchmarking, and human review system.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="h-full bg-slate-50 text-slate-900 font-sans flex">
        <Sidebar />
        <div className="flex-1 lg:pl-64 flex flex-col min-h-screen">
          <Header />
          <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
