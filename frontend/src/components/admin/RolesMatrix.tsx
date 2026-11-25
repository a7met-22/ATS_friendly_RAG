import React, { useEffect, useState } from 'react';
import { Shield, Plus, Trash2 } from 'lucide-react';
import { apiRequest } from '../../api/client';
import type { PermissionItem, RoleItem } from '../../types/api';

export const RolesMatrix: React.FC = () => {
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [catalog, setCatalog] = useState<PermissionItem[]>([]);
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleDesc, setNewRoleDesc] = useState('');
  const [error, setError] = useState('');

  const loadMatrix = async () => {
    try {
      const [rRes, pRes] = await Promise.all([
        apiRequest<{ roles: RoleItem[] }>('/api/v1/admin/roles'),
        apiRequest<{ permissions: PermissionItem[] }>('/api/v1/admin/permissions'),
      ]);
      setRoles(rRes.roles);
      setCatalog(pRes.permissions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load permissions matrix');
    }
  };

  useEffect(() => {
    void loadMatrix();
  }, []);

  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await apiRequest('/api/v1/admin/roles', {
        method: 'POST',
        body: { name: newRoleName, description: newRoleDesc, permissions: ['search_system_documents'] },
      });
      setNewRoleName('');
      setNewRoleDesc('');
      await loadMatrix();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create role');
    }
  };

  const togglePermission = async (role: RoleItem, permCode: string) => {
    if (role.name === 'admin') return;
    const exists = role.permissions.includes(permCode);
    const updated = exists
      ? role.permissions.filter((p) => p !== permCode)
      : [...role.permissions, permCode];

    try {
      await apiRequest(`/api/v1/admin/roles/${role.id}`, {
        method: 'PUT',
        body: { description: role.description, permissions: updated },
      });
      await loadMatrix();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Permission update failed');
    }
  };

  const handleDeleteRole = async (roleId: number) => {
    try {
      await apiRequest(`/api/v1/admin/roles/${roleId}`, { method: 'DELETE' });
      await loadMatrix();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete role failed');
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreateRole} className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
        <div className="flex items-center gap-2 text-indigo-400">
          <Plus className="w-4 h-4" />
          <h3 className="text-sm font-semibold text-slate-100">Create Custom Role</h3>
        </div>
        {error && <p className="text-xs text-rose-400">{error}</p>}
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            required
            placeholder="Role Name (e.g. hr_analyst)"
            value={newRoleName}
            onChange={(e) => setNewRoleName(e.target.value)}
            className="px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
          />
          <input
            type="text"
            placeholder="Description"
            value={newRoleDesc}
            onChange={(e) => setNewRoleDesc(e.target.value)}
            className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-100"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
          >
            Create Role
          </button>
        </div>
      </form>

      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
            <tr>
              <th className="px-4 py-3">Operation / Permission</th>
              {roles.map((r) => (
                <th key={r.id} className="px-4 py-3 text-center">
                  <div className="inline-flex items-center gap-1.5 font-semibold text-slate-200 uppercase">
                    <Shield className="w-3.5 h-3.5 text-indigo-400" />
                    {r.name}
                    {!r.is_system && (
                      <button
                        onClick={() => void handleDeleteRole(r.id)}
                        className="text-slate-500 hover:text-rose-400 ml-1"
                        title="Delete custom role"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {catalog.map((perm) => (
              <tr key={perm.code}>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-200">{perm.label}</div>
                  <div className="text-[11px] text-slate-400">{perm.description}</div>
                </td>
                {roles.map((role) => {
                  const checked = role.permissions.includes(perm.code);
                  return (
                    <td key={role.id} className="px-4 py-3 text-center">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={role.name === 'admin'}
                        onChange={() => void togglePermission(role, perm.code)}
                        className="w-4 h-4 accent-indigo-600 rounded cursor-pointer disabled:opacity-50"
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
