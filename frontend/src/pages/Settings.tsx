import { useUIStore } from '@/stores/uiStore'
import { Card, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge, ProBadge } from '@/components/ui/Badge'

export function Settings() {
  const { theme, setTheme, telemetryOptIn, setTelemetryOptIn } = useUIStore()

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-goose-text">Settings</h1>
        <p className="text-sm text-goose-text-muted mt-1">Configure Goose Flight Forensics</p>
      </div>

      {/* Tier */}
      <Card>
        <CardTitle className="mb-1">License</CardTitle>
        <div className="flex items-center gap-3 mt-3">
          <div className="w-12 h-12 rounded-xl bg-goose-accent/10 flex items-center justify-center">
            <span className="text-2xl">🪿</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-goose-text">Goose Community</span>
              <Badge variant="success">Free</Badge>
            </div>
            <p className="text-xs text-goose-text-muted mt-0.5">All local features unlocked. 17 analysis plugins.</p>
          </div>
        </div>
        <div className="mt-4 p-3 rounded-lg bg-goose-bg border border-goose-border">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-goose-text">Upgrade to Pro</span>
                <ProBadge />
              </div>
              <p className="text-xs text-goose-text-muted mt-0.5">Cloud sync, team collaboration, fleet management, API access</p>
            </div>
            <Button size="sm" variant="secondary">Learn More</Button>
          </div>
        </div>
      </Card>

      {/* Telemetry */}
      <Card>
        <CardTitle className="mb-1">Community Telemetry</CardTitle>
        <CardDescription>
          Help improve drone safety by sharing anonymized analysis results
        </CardDescription>
        <div className="mt-4 space-y-3">
          <label className="flex items-start gap-3 p-3 rounded-lg border border-goose-border hover:border-goose-border-subtle cursor-pointer transition-colors">
            <input
              type="radio"
              name="telemetry"
              checked={telemetryOptIn === true}
              onChange={() => setTelemetryOptIn(true)}
              className="mt-0.5"
            />
            <div>
              <p className="text-sm font-medium text-goose-text">Share anonymized data (recommended)</p>
              <p className="text-xs text-goose-text-muted mt-0.5">
                Health scores, finding types, hardware signatures. No flight paths, GPS coordinates, or pilot identity.
                Helps build the world's largest drone health database.
              </p>
            </div>
          </label>
          <label className="flex items-start gap-3 p-3 rounded-lg border border-goose-border hover:border-goose-border-subtle cursor-pointer transition-colors">
            <input
              type="radio"
              name="telemetry"
              checked={telemetryOptIn === false}
              onChange={() => setTelemetryOptIn(false)}
              className="mt-0.5"
            />
            <div>
              <p className="text-sm font-medium text-goose-text">Keep everything local (air-gapped)</p>
              <p className="text-xs text-goose-text-muted mt-0.5">
                No data leaves your machine. Required for classified or sensitive operations.
              </p>
            </div>
          </label>
        </div>
      </Card>

      {/* Theme */}
      <Card>
        <CardTitle className="mb-4">Theme</CardTitle>
        <div className="grid grid-cols-3 gap-3">
          {[
            { id: 'dark' as const, label: 'Dark', desc: 'Default dark theme', preview: 'bg-[#0B1120]' },
            { id: 'light' as const, label: 'Light', desc: 'Clean light theme', preview: 'bg-gray-100' },
            { id: 'hud' as const, label: 'HUD', desc: 'Green monochrome', preview: 'bg-black' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTheme(t.id)}
              className={`
                p-3 rounded-lg border text-left transition-all cursor-pointer
                ${theme === t.id ? 'border-goose-accent ring-1 ring-goose-accent/50' : 'border-goose-border hover:border-goose-border-subtle'}
              `}
            >
              <div className={`w-full h-8 rounded ${t.preview} border border-goose-border mb-2`} />
              <p className="text-sm font-medium text-goose-text">{t.label}</p>
              <p className="text-[10px] text-goose-text-muted">{t.desc}</p>
            </button>
          ))}
        </div>
      </Card>

      {/* Analysis Defaults */}
      <Card>
        <CardTitle className="mb-4">Default Analysis Profile</CardTitle>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { id: 'default', label: 'Default', icon: '🎯' },
            { id: 'racer', label: 'Racer', icon: '🏁' },
            { id: 'shop', label: 'Shop', icon: '🔧' },
            { id: 'advanced', label: 'Advanced', icon: '⚡' },
          ].map((p) => (
            <button
              key={p.id}
              className="p-3 rounded-lg border border-goose-border hover:border-goose-border-subtle text-left cursor-pointer transition-colors"
            >
              <span className="text-lg">{p.icon}</span>
              <p className="text-sm font-medium text-goose-text mt-1">{p.label}</p>
            </button>
          ))}
        </div>
      </Card>

      {/* About */}
      <Card>
        <CardTitle className="mb-3">About</CardTitle>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <span className="text-goose-text-muted">Version</span>
          <span className="text-goose-text font-mono">1.3.5</span>
          <span className="text-goose-text-muted">Engine</span>
          <span className="text-goose-text">Goose Flight Core</span>
          <span className="text-goose-text-muted">Plugins</span>
          <span className="text-goose-text">11 Core + 6 Pro</span>
          <span className="text-goose-text-muted">License</span>
          <span className="text-goose-text">Apache 2.0 (Core)</span>
          <span className="text-goose-text-muted">Website</span>
          <a href="https://flygoose.dev" target="_blank" className="text-goose-accent hover:underline">flygoose.dev</a>
        </div>
      </Card>
    </div>
  )
}
