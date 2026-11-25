import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  apiRequest,
  getAuthToken,
  getGuestSessionId,
  rotateGuestSessionId,
  setAuthToken,
} from '../api/client';
import type { UserProfile } from '../types/api';

interface AuthContextValue {
  user: UserProfile | null;
  sessionId: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
  can: (permissionCode: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [sessionId, setSessionId] = useState<string>(() => getGuestSessionId());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshProfile = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const res = await apiRequest<{ authenticated: boolean; user: UserProfile | null }>('/api/v1/auth/me');
      if (res.authenticated && res.user) {
        setUser(res.user);
      } else {
        setAuthToken(null);
        setUser(null);
      }
    } catch {
      setAuthToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshProfile();
  }, [refreshProfile]);

  const login = async (email: string, password: string) => {
    const res = await apiRequest<{ access_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    const newSid = rotateGuestSessionId();
    setSessionId(newSid);
    setAuthToken(res.access_token);
    await refreshProfile();
  };

  const logout = () => {
    setAuthToken(null);
    setUser(null);
    const freshGuestSid = rotateGuestSessionId();
    setSessionId(freshGuestSid);
  };

  const can = useCallback(
    (permissionCode: string) => {
      if (!user) return false;
      return user.permissions.includes(permissionCode);
    },
    [user]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        sessionId,
        isAuthenticated: Boolean(user),
        isLoading,
        login,
        logout,
        refreshProfile,
        can,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
