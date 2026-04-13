import { useState, useEffect } from 'react'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { User } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function roleVariant(role: User['role']) {
  switch (role) {
    case 'admin': return 'error' as const
    case 'lead_engineer': return 'accent' as const
    case 'analyst': return 'info' as const
    case 'viewer': return 'default' as const
  }
}

function statusVariant(status: User['status']) {
  return status === 'active' ? 'success' as const : 'default' as const
}

const ROLES: User['role'][] = ['admin', 'lead_engineer', 'analyst', 'viewer']

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    password: '',
    role: 'analyst' as User['role'],
  })

  const hasToken = !!localStorage.getItem('goose_pro_token')

  const fetchUsers = async () => {
    try {
      setError(null)
      const data = await proApi.get<User[]>('/api/auth/users')
      setUsers(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (hasToken) fetchUsers()
    else setLoading(false)
  }, [hasToken])

  const handleAdd = async () => {
    if (!form.username.trim()) return
    setSaving(true)
    try {
      await proApi.post('/api/auth/users', form)
      setForm({ username: '', display_name: '', password: '', role: 'analyst' })
      setShowForm(false)
      setLoading(true)
      await fetchUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
            Users &amp; Roles <ProBadge />
          </h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Manage Pro server access and role assignments
          </p>
        </div>
        {hasToken && <Button onClick={() => setShowForm(true)}>+ Add User</Button>}
      </div>

      {/* Not logged in */}
      {!hasToken && (
        <Card className="border-goose-warning/30 bg-goose-warning/5">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-goose-warning shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <div>
              <p className="text-sm font-medium text-goose-warning">Pro Authentication Required</p>
              <p className="text-xs text-goose-text-muted mt-1">
                Set a <code className="font-mono text-goose-text">goose_pro_token</code> in localStorage to access
                user management. Obtain a token from your Pro server administrator.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Add user form */}
      {showForm && (
        <Card className="border-goose-accent/30 bg-goose-accent/5">
          <CardTitle className="mb-4">Add New User</CardTitle>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Username *</label>
              <input
                value={form.username}
                onChange={e => setForm({ ...form, username: e.target.value })}
                placeholder="e.g. jsmith"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text font-mono placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Display Name</label>
              <input
                value={form.display_name}
                onChange={e => setForm({ ...form, display_name: e.target.value })}
                placeholder="e.g. John Smith"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Password *</label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })}
                placeholder="Temporary password"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Role</label>
              <select
                value={form.role}
                onChange={e => setForm({ ...form, role: e.target.value as User['role'] })}
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
              >
                {ROLES.map(r => (
                  <option key={r} value={r}>{r.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="secondary" onClick={() => { setShowForm(false); setForm({ username: '', display_name: '', password: '', role: 'analyst' }) }}>
              Cancel
            </Button>
            <Button loading={saving} onClick={handleAdd} disabled={!form.username.trim() || !form.password.trim()}>
              Add User
            </Button>
          </div>
        </Card>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {loading && hasToken && (
        <div className="flex items-center justify-center h-64"><LoadingSpinner /></div>
      )}

      {!loading && hasToken && users.length === 0 && (
        <div className="text-center py-16 text-goose-text-muted">
          <p className="text-lg font-medium text-goose-text">No Users Found</p>
          <p className="text-sm mt-2">Add the first user to enable Pro server access control.</p>
        </div>
      )}

      {!loading && hasToken && users.length > 0 && (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Username</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Display Name</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Role</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Last Login</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {users.map(user => (
                  <tr key={user.user_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                    <td className="px-4 py-3 font-mono text-goose-text text-xs">{user.username}</td>
                    <td className="px-4 py-3 text-goose-text">{user.display_name || '—'}</td>
                    <td className="px-4 py-3">
                      <Badge variant={roleVariant(user.role)}>{user.role.replace('_', ' ')}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={statusVariant(user.status)}>{user.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-goose-text-muted text-xs">
                      {user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}
                    </td>
                    <td className="px-4 py-3">
                      <Button size="sm" variant="ghost">Edit</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
