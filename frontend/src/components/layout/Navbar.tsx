import React, { useEffect, useState } from 'react';
import { Bot, LogIn, LogOut, ShieldCheck, Activity } from 'lucide-react';
import { apiRequest } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

interface NavbarProps {
  activeTab: 'workspace' | 'admin';
  setActiveTab: (tab: 'workspace' | 'admin') => void;
  onOpenAuth: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, onOpenAuth }) => {
  const { user, isAuthenticated, logout, can } = useAuth();
  const [healthy, setHealthy] = useState<boolean | null>(null);

  const hasAdminAccess =
    can('system:sync') || can('admin:manage_users') || can('admin:manage_roles');

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await apiRequest<{ status: string }>('/health');
        setHealthy(res.status === 'healthy');
      } catch {
        setHealthy(false);
      }
    };
    void checkHealth();
    const timer = setInterval(checkHealth, 30000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
          <Bot className="w-5 h-5" />
        </div>
        <div>
          <h1 className="font-semibold text-slate-100 text-base">ResumeRAG AI</h1>
          <p className="text-xs text-slate-400">Enterprise Talent Intelligence</p>
        </div>

        <div className="ml-4 flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-slate-800 border border-slate-700">
          <Activity
            className={`w-3.5 h-3.5 ${
              healthy ? 'text-emerald-400' : healthy === false ? 'text-rose-400' : 'text-amber-400'
            }`}
          />
          <span className="text-slate-300">
            {healthy ? 'System Online' : healthy === false ? 'Offline' : 'Checking...'}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {hasAdminAccess && (
          <nav className="flex bg-slate-800 p-1 rounded-lg border border-slate-700">
            <button
              onClick={() => setActiveTab('workspace')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                activeTab === 'workspace' ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:text-white'
              }`}
            >
              AI Workspace
            </button>
            <button
              onClick={() => setActiveTab('admin')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition ${
                activeTab === 'admin' ? 'bg-indigo-600 text-white' : 'text-slate-300 hover:text-white'
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              Admin Panel
            </button>
          </nav>
        )}

        {isAuthenticated && user ? (
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-medium text-slate-200">{user.full_name || user.email}</div>
              <div className="text-[11px] text-indigo-400 uppercase">{user.roles.join(', ')}</div>
            </div>
            <button
              onClick={logout}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/60 text-slate-300 hover:text-rose-300 border border-slate-700 text-xs flex items-center gap-1.5 transition"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium flex items-center gap-1.5 transition"
          >
            <LogIn className="w-3.5 h-3.5" />
            Staff Sign In
          </button>
        )}
      </div>
    </header>
  );
};
