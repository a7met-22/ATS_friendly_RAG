import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { DriveSyncCard } from './DriveSyncCard';
import { UsersManager } from './UsersManager';
import { RolesMatrix } from './RolesMatrix';

export const AdminDashboard: React.FC = () => {
  const { can } = useAuth();
  const canSync = can('system:sync');
  const canUsers = can('admin:manage_users');
  const canRoles = can('admin:manage_roles');

  const defaultTab: 'sync' | 'users' | 'roles' = canSync
    ? 'sync'
    : canUsers
    ? 'users'
    : 'roles';
  const [tab, setTab] = useState<'sync' | 'users' | 'roles'>(defaultTab);

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">System Administration &amp; RBAC</h2>
            <p className="text-xs text-slate-400">
              Manage Google Drive synchronization, user accounts, and granular role permissions.
            </p>
          </div>
          <div className="flex gap-2 bg-slate-900 p-1 rounded-xl border border-slate-800">
            {canSync && (
              <button
                onClick={() => setTab('sync')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab === 'sync' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Drive Sync
              </button>
            )}
            {canUsers && (
              <button
                onClick={() => setTab('users')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab === 'users' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Users
              </button>
            )}
            {canRoles && (
              <button
                onClick={() => setTab('roles')}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab === 'roles' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Roles &amp; Permissions
              </button>
            )}
          </div>
        </div>
        {tab === 'sync' && canSync && <DriveSyncCard />}
        {tab === 'users' && canUsers && <UsersManager />}
        {tab === 'roles' && canRoles && <RolesMatrix />}
      </div>
    </div>
  );
};
