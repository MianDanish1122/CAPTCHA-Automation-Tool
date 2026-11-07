'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, getStoredToken, getStoredUser, setStoredToken, setStoredUser } from './api';
import { UserProfile, LoginResponse } from './types';

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isOperator: boolean;
  login: (username: string, password: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Initialize auth state from local storage on mount
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = getStoredToken();
      const storedUser = getStoredUser();

      if (storedToken) {
        setToken(storedToken);
        if (storedUser) setUser(storedUser);

        try {
          // Verify token validity with server
          const meRes = await api.getMe();
          if (meRes.user) {
            setUser(meRes.user);
            setStoredUser(meRes.user);
          }
        } catch {
          // Invalid or expired token
          setStoredToken(null);
          setStoredUser(null);
          setToken(null);
          setUser(null);
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<LoginResponse> => {
    setIsLoading(true);
    try {
      const res = await api.login({ username, password });
      setToken(res.access_token);
      setUser(res.user);
      return res;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await api.logout();
    } finally {
      setToken(null);
      setUser(null);
      setIsLoading(false);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const meRes = await api.getMe();
      if (meRes.user) {
        setUser(meRes.user);
        setStoredUser(meRes.user);
      }
    } catch {
      // Ignore
    }
  }, []);

  const isAuthenticated = !!token && !!user;
  const isAdmin = user?.role === 'admin';
  const isOperator = user?.role === 'operator';

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated,
        isAdmin,
        isOperator,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
