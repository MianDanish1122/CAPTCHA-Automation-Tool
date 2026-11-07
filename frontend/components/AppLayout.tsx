'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import { Shield } from 'lucide-react';

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  const isLoginPage = pathname === '/login';

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !isLoginPage) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, isLoginPage, router]);

  // If on login page, display standalone without navigation layout
  if (isLoginPage) {
    return <>{children}</>;
  }

  // Loading state while verifying token
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-white">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/25 mb-4 animate-bounce">
          <Shield className="w-6 h-6" />
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400 font-medium">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span>Verifying security credentials...</span>
        </div>
      </div>
    );
  }

  // If not authenticated and waiting for redirect, render nothing or minimal placeholder
  if (!isAuthenticated) {
    return null;
  }

  // Authenticated application shell
  return (
    <div className="flex min-h-screen w-full bg-slate-50">
      <Sidebar />
      <div className="flex-1 lg:pl-64 flex flex-col min-h-screen w-full">
        <Header />
        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
