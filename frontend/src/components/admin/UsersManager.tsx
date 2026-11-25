import React, { useEffect, useState } from 'react';
import { UserPlus } from 'lucide-react';
import { apiRequest } from '../../api/client';
import type { AdminUserItem, RoleItem } from '../../types/api';

export const UsersManager: React.FC = () => {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [roleId, setRoleId] = useState<number>(0);
  const [error, setError] = useState('');

  const loadData = async () => {
    try {
      const [uRes, rRes] = await Promise.all([
        apiRequest<{ users: AdminUserItem[] }>('/api/v1/admin/users'),
        apiRequest<{ roles: RoleItem[] }>('/api/v1/admin/roles'),
      ]);
      setUsers(uRes.users);
      setRoles(rRes.roles);
      if (rRes.roles.length > 0 && roleId === 0) {
        setRoleId(rRes.roles.at(0)!.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await apiRequest('/api/v1/admin/users', {
        method: 'POST',
        body: { email, full_name: fullName, password, role_id: roleId },
      });
      setEmail('');
      setFullName('');
      setPassword('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user');
    }
  };

  const handleToggleActive = async (user: AdminUserItem) => {
    try {
      await apiRequest(`/api/v1/admin/users/${user.id}`, {
        method: 'PATCH',
        body: { is_active: !user.is_active },
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
  };

  const handleChangeRole = async (userId: number, newRoleId: number) => {
    try {
      await apiRequest(`/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        body: { role_id: newRoleId },
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Role update failed');
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreateUser} className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
        <div className="flex items-center gap-2 text-indigo-400">
          <UserPlus className="w-4 h-4" />
          <h3 className="text-sm font-semibold text-slate-100">Register New System User</h3>
        </div>
        {error && <p className="text-xs text-rose-400">{error}</p>}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <input
            type="text"
            required
            placeholder="Full Name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
          />
          <input
            type="email"
            required
            placeholder="Email Address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
          />
          <input
            type="password"
            required
            minLength={8}
            placeholder="Password (min 8 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
          />
          <div className="flex gap-2">
            <select
              value={roleId}
              onChange={(e) => setRoleId(Number(e.target.value))}
              className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
            >
              Add
            </button>
          </div>
        </div>
      </form>

      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
            <tr>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Assigned Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-200">{u.full_name}</div>
                  <div className="text-slate-400">{u.email}</div>
                </td>
                <td className="px-4 py-3">
                  <select
                    value={u.role_id}
                    onChange={(e) => void handleChangeRole(u.id, Number(e.target.value))}
                    className="px-2.5 py-1 rounded bg-slate-950 border border-slate-700 text-slate-200"
                  >
                    {roles.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[11px] ${
                      u.is_active ? 'bg-emerald-950 text-emerald-300' : 'bg-rose-950 text-rose-300'
                    }`}
                  >
                    {u.is_active ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => void handleToggleActive(u)}
                    className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200"
                  >
                    {u.is_active ? 'Disable' : 'Enable'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
