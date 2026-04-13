import { useState, useEffect } from 'react'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import { ProBadge } from '@/components/ui/Badge'
import { proApi } from '@/lib/proApi'
import type { DroneProfile, NavSystemProfile } from '@/lib/proTypes'

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-6 w-6 text-goose-accent" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function droneStatusVariant(status: DroneProfile['status']) {
  switch (status) {
    case 'active': return 'success' as const
    case 'maintenance': return 'warning' as const
    case 'retired': return 'default' as const
  }
}

function techVariant(tech: string) {
  const t = tech.toLowerCase()
  if (t.includes('vio')) return 'accent' as const
  if (t.includes('trn')) return 'info' as const
  if (t.includes('slam')) return 'warning' as const
  return 'default' as const
}

// --- Drones Tab ---
function DronesTab() {
  const [drones, setDrones] = useState<DroneProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: '', vehicle_type: '', serial_number: '' })

  const fetchDrones = async () => {
    try {
      setError(null)
      const data = await proApi.get<DroneProfile[]>('/api/fleet/drones')
      setDrones(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load drones')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDrones() }, [])

  const handleRegister = async () => {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      await proApi.post('/api/fleet/drones', form)
      setForm({ name: '', vehicle_type: '', serial_number: '' })
      setShowForm(false)
      setLoading(true)
      await fetchDrones()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to register drone')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowForm(true)}>+ Register Drone</Button>
      </div>

      {showForm && (
        <Card className="border-goose-accent/30 bg-goose-accent/5">
          <CardTitle className="mb-4">Register Drone</CardTitle>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Name *</label>
              <input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Test Platform Alpha"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Vehicle Type</label>
              <input
                value={form.vehicle_type}
                onChange={e => setForm({ ...form, vehicle_type: e.target.value })}
                placeholder="e.g. quadrotor, vtol"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Serial Number</label>
              <input
                value={form.serial_number}
                onChange={e => setForm({ ...form, serial_number: e.target.value })}
                placeholder="Optional"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text font-mono placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="secondary" onClick={() => { setShowForm(false); setForm({ name: '', vehicle_type: '', serial_number: '' }) }}>Cancel</Button>
            <Button loading={saving} onClick={handleRegister} disabled={!form.name.trim()}>Register</Button>
          </div>
        </Card>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-40"><LoadingSpinner /></div>
      ) : drones.length === 0 ? (
        <div className="text-center py-16 text-goose-text-muted">
          <p className="text-lg font-medium text-goose-text">No Drones Registered</p>
          <p className="text-sm mt-2">Register a drone to associate it with test campaigns.</p>
        </div>
      ) : (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Name</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Type</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Serial</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Nav System</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {drones.map(drone => (
                  <tr key={drone.drone_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                    <td className="px-4 py-3 font-medium text-goose-text">{drone.name}</td>
                    <td className="px-4 py-3 text-goose-text-secondary">{drone.vehicle_type || '—'}</td>
                    <td className="px-4 py-3 font-mono text-goose-text-muted text-xs">{drone.serial_number || '—'}</td>
                    <td className="px-4 py-3">
                      <Badge variant={droneStatusVariant(drone.status)}>{drone.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-goose-text-secondary text-xs font-mono">{drone.nav_system_id || '—'}</td>
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

// --- Nav Systems Tab ---
function NavSystemsTab() {
  const [systems, setSystems] = useState<NavSystemProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ name: '', vendor: '', technology: '', firmware_version: '' })

  const fetchSystems = async () => {
    try {
      setError(null)
      const data = await proApi.get<NavSystemProfile[]>('/api/fleet/nav-systems')
      setSystems(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load nav systems')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchSystems() }, [])

  const handleAdd = async () => {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      await proApi.post('/api/fleet/nav-systems', form)
      setForm({ name: '', vendor: '', technology: '', firmware_version: '' })
      setShowForm(false)
      setLoading(true)
      await fetchSystems()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add nav system')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowForm(true)}>+ Add Nav System</Button>
      </div>

      {showForm && (
        <Card className="border-goose-accent/30 bg-goose-accent/5">
          <CardTitle className="mb-4">Add Nav System</CardTitle>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Name *</label>
              <input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. VectorNav VN-300"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Vendor</label>
              <input
                value={form.vendor}
                onChange={e => setForm({ ...form, vendor: e.target.value })}
                placeholder="e.g. VectorNav"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Technology</label>
              <input
                value={form.technology}
                onChange={e => setForm({ ...form, technology: e.target.value })}
                placeholder="e.g. VIO, TRN, SLAM, INS"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
            <div>
              <label className="text-xs text-goose-text-muted block mb-1">Firmware Version</label>
              <input
                value={form.firmware_version}
                onChange={e => setForm({ ...form, firmware_version: e.target.value })}
                placeholder="e.g. 1.0.4"
                className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text font-mono placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button variant="secondary" onClick={() => { setShowForm(false); setForm({ name: '', vendor: '', technology: '', firmware_version: '' }) }}>Cancel</Button>
            <Button loading={saving} onClick={handleAdd} disabled={!form.name.trim()}>Add System</Button>
          </div>
        </Card>
      )}

      {error && (
        <div className="p-4 rounded-lg bg-goose-error/10 border border-goose-error/30 text-goose-error text-sm">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-40"><LoadingSpinner /></div>
      ) : systems.length === 0 ? (
        <div className="text-center py-16 text-goose-text-muted">
          <p className="text-lg font-medium text-goose-text">No Nav Systems Registered</p>
          <p className="text-sm mt-2">Add nav systems to track which technology was tested in each campaign.</p>
        </div>
      ) : (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-goose-border">
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Name</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Vendor</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Technology</th>
                  <th className="text-left px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Firmware</th>
                  <th className="text-right px-4 py-3 text-xs text-goose-text-muted uppercase tracking-wide">Claimed CEP</th>
                </tr>
              </thead>
              <tbody>
                {systems.map(sys => {
                  const claimedCep = sys.specifications?.claimed_cep_m as number | undefined
                  return (
                    <tr key={sys.profile_id} className="border-b border-goose-border last:border-0 hover:bg-goose-surface-hover">
                      <td className="px-4 py-3 font-medium text-goose-text">{sys.name}</td>
                      <td className="px-4 py-3 text-goose-text-secondary">{sys.vendor || '—'}</td>
                      <td className="px-4 py-3">
                        {sys.technology ? (
                          <Badge variant={techVariant(sys.technology)}>{sys.technology.toUpperCase()}</Badge>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-goose-text-muted text-xs">{sys.firmware_version || '—'}</td>
                      <td className="px-4 py-3 text-right font-mono text-goose-text">
                        {claimedCep !== undefined ? `${claimedCep.toFixed(1)} m` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

// --- Main Page ---
export function FleetProPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-goose-text flex items-center gap-3">
          Fleet &amp; Nav Systems <ProBadge />
        </h1>
        <p className="text-sm text-goose-text-muted mt-1">
          Register drones and nav system profiles for use in validation campaigns
        </p>
      </div>

      <Tabs
        tabs={[
          { id: 'drones', label: 'Drones' },
          { id: 'nav-systems', label: 'Nav Systems' },
        ]}
      >
        {tab => (
          <>
            {tab === 'drones' && <DronesTab />}
            {tab === 'nav-systems' && <NavSystemsTab />}
          </>
        )}
      </Tabs>
    </div>
  )
}
