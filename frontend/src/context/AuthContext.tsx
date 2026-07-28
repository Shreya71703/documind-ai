/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiRequest } from '../lib/api';

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  loginGuest: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchMeInternal = async (): Promise<boolean> => {
    try {
      const data = await apiRequest('/api/v1/auth/me');
      setUser(data);
      return true;
    } catch {
      localStorage.removeItem('documind_token');
      return false;
    }
  };

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiRequest('/api/v1/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    localStorage.setItem('documind_token', data.access_token);
    await fetchMeInternal();
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await apiRequest('/api/v1/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password, full_name: email.split('@')[0] }),
    });
    await login(email, password);
  }, [login]);

  const loginGuest = useCallback(async () => {
    const guestEmail = 'guest@documind.ai';
    const guestPass = 'guestpassword123';
    try {
      await login(guestEmail, guestPass);
    } catch {
      try {
        await register(guestEmail, guestPass);
      } catch {
        setUser({
          id: 'guest-session-id',
          email: 'guest@documind.ai',
          full_name: 'Guest User',
          is_active: true,
          is_admin: false,
        });
      }
    }
  }, [login, register]);

  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      const token = localStorage.getItem('documind_token');
      if (token) {
        const ok = await fetchMeInternal();
        if (!ok && isMounted) {
          await loginGuest();
        }
      } else if (isMounted) {
        await loginGuest();
      }
      if (isMounted) {
        setIsLoading(false);
      }
    };

    initAuth();

    return () => {
      isMounted = false;
    };
  }, [loginGuest]);

  const logout = () => {
    localStorage.removeItem('documind_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        loginGuest,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
