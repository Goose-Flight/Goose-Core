import { useState } from 'react'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { KPICard } from '@/components/ui/KPICard'
import type { Drone } from '@/lib/types'

// Local-only fleet for now (no backend route yet)
const STORAGE_KEY = 'goose-fleet'

function loadFleet(): Drone[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch { return [] }
}

function saveFleet(fleet: Drone[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(fleet))
}

const droneTypes = [
  { value: 'quad', label: 'Quadcopter', icon: '🚁' },
  { value: 'hex', label: 'Hexacopter', icon: '🔷' },
  { value: 'octo', label: 'Octocopter', icon: '⬡' },
  { value: 'vtol', label: 'VTOL', icon: '✈️' },
  { value: 'fixed-wing', label: 'Fixed Wing', icon: '🛩️' },
  { value: 'other', label: 'Other', icon: '🛸' },
]

export function Fleet() {
  const [fleet, setFleet] = useState<Drone[]>(loadFleet)
  const [showModal, setShowModal] = useState(false)
  const [newDrone, setNewDrone] = useState({
    name: '', type: 'quad', make: '', model: '', serial: '', notes: '',
    battery_cell_count: 4, battery_capacity: 5000,
  })

  const handleAdd = () => {
    const drone: Drone = {
      drone_id: `DRN-${Date.now().toString(36).toUpperCase()}`,
      name: newDrone.name || 'Unnamed Drone',
      type: newDrone.type,
      make: newDrone.make,
      model: newDrone.model,
      serial: newDrone.serial,
      status: 'active',
      flight_count: 0,
      total_hours: 0,
      notes: newDrone.notes,
      battery_info: {
        cell_count: newDrone.battery_cell_count,
        capacity_mah: newDrone.battery_capacity,
      },
    }
    const updated = [...fleet, drone]
    setFleet(updated)
    saveFleet(updated)
    setShowModal(false)
    setNewDrone({ name: '', type: 'quad', make: '', model: '', serial: '', notes: '', battery_cell_count: 4, battery_capacity: 5000 })
  }

  const handleDelete = (id: string) => {
    const updated = fleet.filter(d => d.drone_id !== id)
    setFleet(updated)
    saveFleet(updated)
  }

  const totalFlights = fleet.reduce((s, d) => s + d.flight_count, 0)
  const totalHours = fleet.reduce((s, d) => s + d.total_hours, 0)

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-goose-text">Drone Fleet</h1>
          <p className="text-sm text-goose-text-muted mt-1">
            Register your drones and associate flights with specific airframes
          </p>
        </div>
        <Button onClick={() => setShowModal(true)}>+ Add Drone</Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="Fleet Size" value={fleet.length} />
        <KPICard label="Active" value={fleet.filter(d => d.status === 'active').length} status="healthy" />
        <KPICard label="Total Flights" value={totalFlights} />
        <KPICard label="Total Hours" value={totalHours.toFixed(1)} />
      </div>

      {/* Empty state */}
      {fleet.length === 0 && (
        <Card className="py-16 text-center">
          <span className="text-5xl block mb-4">🚁</span>
          <p className="text-lg font-medium text-goose-text">No Drones Registered</p>
          <p className="text-sm text-goose-text-muted mt-2 max-w-md mx-auto">
            Add your drones to track per-airframe flight history, health trends, and maintenance intervals.
          </p>
          <Button className="mt-6" onClick={() => setShowModal(true)}>
            Add Your First Drone
          </Button>
        </Card>
      )}

      {/* Fleet Grid */}
      {fleet.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {fleet.map((drone) => {
            const typeInfo = droneTypes.find(t => t.value === drone.type) || droneTypes[5]
            return (
              <Card key={drone.drone_id} className="relative group">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-goose-accent/10 flex items-center justify-center text-2xl">
                      {typeInfo.icon}
                    </div>
                    <div>
                      <p className="text-sm font-bold text-goose-text">{drone.name}</p>
                      <p className="text-xs text-goose-text-muted">{typeInfo.label}</p>
                    </div>
                  </div>
                  <Badge variant={drone.status === 'active' ? 'success' : drone.status === 'maintenance' ? 'warning' : 'default'}>
                    {drone.status}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-4 text-xs">
                  {drone.make && (
                    <>
                      <span className="text-goose-text-muted">Make/Model</span>
                      <span className="text-goose-text">{drone.make} {drone.model}</span>
                    </>
                  )}
                  {drone.serial && (
                    <>
                      <span className="text-goose-text-muted">Serial</span>
                      <span className="text-goose-text font-mono">{drone.serial}</span>
                    </>
                  )}
                  <span className="text-goose-text-muted">Flights</span>
                  <span className="text-goose-text">{drone.flight_count}</span>
                  <span className="text-goose-text-muted">Hours</span>
                  <span className="text-goose-text">{drone.total_hours.toFixed(1)}</span>
                  {drone.battery_info && (
                    <>
                      <span className="text-goose-text-muted">Battery</span>
                      <span className="text-goose-text">{drone.battery_info.cell_count}S {drone.battery_info.capacity_mah}mAh</span>
                    </>
                  )}
                </div>

                <div className="flex justify-end mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button size="sm" variant="danger" onClick={() => handleDelete(drone.drone_id)}>
                    Remove
                  </Button>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* Add Drone Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <Card className="w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <CardTitle className="mb-1">Add New Drone</CardTitle>
            <CardDescription>Register an aircraft in your fleet</CardDescription>

            <div className="mt-6 space-y-4">
              {/* Name */}
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Drone Name *</label>
                <input
                  value={newDrone.name}
                  onChange={(e) => setNewDrone({ ...newDrone, name: e.target.value })}
                  placeholder="e.g. Survey Quad #1"
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
                />
              </div>

              {/* Type */}
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Type</label>
                <div className="grid grid-cols-3 gap-2">
                  {droneTypes.map((t) => (
                    <button
                      key={t.value}
                      onClick={() => setNewDrone({ ...newDrone, type: t.value })}
                      className={`p-2 rounded-lg border text-center cursor-pointer transition-all ${
                        newDrone.type === t.value
                          ? 'border-goose-accent bg-goose-accent/5'
                          : 'border-goose-border hover:border-goose-border-subtle'
                      }`}
                    >
                      <span className="text-xl">{t.icon}</span>
                      <p className="text-[10px] text-goose-text mt-0.5">{t.label}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* Make / Model */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-goose-text-muted block mb-1">Make</label>
                  <input
                    value={newDrone.make}
                    onChange={(e) => setNewDrone({ ...newDrone, make: e.target.value })}
                    placeholder="e.g. DJI, Holybro"
                    className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
                  />
                </div>
                <div>
                  <label className="text-xs text-goose-text-muted block mb-1">Model</label>
                  <input
                    value={newDrone.model}
                    onChange={(e) => setNewDrone({ ...newDrone, model: e.target.value })}
                    placeholder="e.g. X500 V2"
                    className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
                  />
                </div>
              </div>

              {/* Serial */}
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Serial Number</label>
                <input
                  value={newDrone.serial}
                  onChange={(e) => setNewDrone({ ...newDrone, serial: e.target.value })}
                  placeholder="Optional"
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text font-mono placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent"
                />
              </div>

              {/* Battery */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-goose-text-muted block mb-1">Battery Cells (S)</label>
                  <select
                    value={newDrone.battery_cell_count}
                    onChange={(e) => setNewDrone({ ...newDrone, battery_cell_count: Number(e.target.value) })}
                    className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
                  >
                    {[2, 3, 4, 5, 6, 8, 10, 12].map((s) => (
                      <option key={s} value={s}>{s}S ({(s * 4.2).toFixed(1)}V)</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-goose-text-muted block mb-1">Capacity (mAh)</label>
                  <input
                    type="number"
                    value={newDrone.battery_capacity}
                    onChange={(e) => setNewDrone({ ...newDrone, battery_capacity: Number(e.target.value) })}
                    className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text focus:outline-none focus:border-goose-accent"
                  />
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="text-xs text-goose-text-muted block mb-1">Notes</label>
                <textarea
                  value={newDrone.notes}
                  onChange={(e) => setNewDrone({ ...newDrone, notes: e.target.value })}
                  placeholder="Props, ESCs, FC, payload, etc."
                  rows={2}
                  className="w-full bg-goose-bg border border-goose-border rounded-lg px-3 py-2 text-sm text-goose-text placeholder:text-goose-text-muted focus:outline-none focus:border-goose-accent resize-y"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <Button variant="secondary" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button onClick={handleAdd} disabled={!newDrone.name.trim()}>Add Drone</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
