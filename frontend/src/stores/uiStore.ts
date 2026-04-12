import { create } from 'zustand'

type AppMode = 'quick' | 'investigation'
type Theme = 'dark' | 'light' | 'hud'

interface UIState {
  mode: AppMode
  theme: Theme
  sidebarCollapsed: boolean
  telemetryOptIn: boolean | null // null = not yet decided

  setMode: (mode: AppMode) => void
  setTheme: (theme: Theme) => void
  toggleSidebar: () => void
  setTelemetryOptIn: (v: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  mode: 'quick',
  theme: 'dark',
  sidebarCollapsed: false,
  telemetryOptIn: null,

  setMode: (mode) => set({ mode }),
  setTheme: (theme) => set({ theme }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setTelemetryOptIn: (v) => set({ telemetryOptIn: v }),
}))
