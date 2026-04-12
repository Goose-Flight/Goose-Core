import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Dashboard } from '@/pages/Dashboard'
import { UploadWizard } from '@/pages/UploadWizard'
import { QuickResults } from '@/pages/QuickResults'
import { MotorAnalysis } from '@/pages/subsystems/MotorAnalysis'
import { BatteryAnalysis } from '@/pages/subsystems/BatteryAnalysis'
import { GPSAnalysis } from '@/pages/subsystems/GPSAnalysis'
import { VibrationAnalysis } from '@/pages/subsystems/VibrationAnalysis'
import { ControlAnalysis } from '@/pages/subsystems/ControlAnalysis'
import { EnvironmentAnalysis } from '@/pages/subsystems/EnvironmentAnalysis'
import { AnomalyTimeline } from '@/pages/AnomalyTimeline'
import { FlightPath3D } from '@/pages/FlightPath3D'
import { CaseList } from '@/pages/cases/CaseList'
import { CreateCase } from '@/pages/cases/CreateCase'
import { CaseDetail } from '@/pages/cases/CaseDetail'
import { Settings } from '@/pages/Settings'
import { Fleet } from '@/pages/Fleet'

function ComingSoon({ title }: { title: string }) {
  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-goose-text">{title}</h1>
      <p className="text-sm text-goose-text-muted mt-2">This page is coming soon.</p>
    </div>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },

      // Quick Analysis
      { path: 'analyze', element: <UploadWizard /> },
      { path: 'analyze/:analysisId', element: <QuickResults /> },

      // Subsystem pages
      { path: 'analyze/:analysisId/motors', element: <MotorAnalysis /> },
      { path: 'analyze/:analysisId/battery', element: <BatteryAnalysis /> },
      { path: 'analyze/:analysisId/gps', element: <GPSAnalysis /> },
      { path: 'analyze/:analysisId/vibration', element: <VibrationAnalysis /> },
      { path: 'analyze/:analysisId/control', element: <ControlAnalysis /> },
      { path: 'analyze/:analysisId/environment', element: <EnvironmentAnalysis /> },
      { path: 'analyze/:analysisId/flight-path', element: <FlightPath3D /> },
      { path: 'analyze/:analysisId/timeline', element: <AnomalyTimeline /> },
      { path: 'analyze/:analysisId/replay', element: <ComingSoon title="Flight Replay (MapLibre GL)" /> },

      // Investigation
      { path: 'cases', element: <CaseList /> },
      { path: 'cases/new', element: <CreateCase /> },
      { path: 'cases/:caseId', element: <CaseDetail /> },

      // Fleet
      { path: 'fleet', element: <Fleet /> },

      // Settings
      { path: 'settings', element: <Settings /> },
    ],
  },
])
