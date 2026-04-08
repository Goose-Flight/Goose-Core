# Goose Claude Pack 03 - GUI and Workflow Spec

## Purpose

This document defines how Goose should work as a product from the user’s perspective.
It treats the web GUI as the primary product surface and describes the required screens, workflows, user types, deployment modes, and interaction patterns.

Claude must not treat the GUI as an afterthought.
The GUI must be designed around the forensic case workflow.

---

## 1. Product Surface Rule

The web GUI is the main way users use Goose.
The CLI exists for automation, debugging, testing, batch operations, and admin workflows, but it is not the primary user surface.

### Rule
Anything important in Goose must be operable from the web GUI.
The GUI should not be a thin shell over hidden CLI-only capabilities.

### Core architectural rule
The GUI must call the same case-oriented forensic services used by the CLI and future portal workflows.
Do not build GUI-only business logic that bypasses the core.

---

## 2. Primary User Journey

The normal investigation workflow in the GUI should be:

1. user lands on dashboard
2. user creates or opens a case
3. user uploads or attaches evidence
4. user reviews evidence metadata and integrity
5. user runs parse
6. user reviews parse diagnostics and data quality
7. user runs analysis
8. user reviews findings and supporting evidence
9. user explores timeline and charts
10. user reviews hypotheses / root-cause view
11. user adds notes or disposition if allowed
12. user exports case bundle or report
13. user can replay later if needed

This flow should feel obvious and guided.

---

## 3. UX Principles

Claude should design the GUI with these principles:

### 3.1 Case-oriented workflow
Everything should center around cases.
Evidence, findings, charts, timeline, notes, reports, and exports should all live within the case context.

### 3.2 Integrity visible early
Evidence hashes, parser confidence, warnings, corruption, and missing data should be visible early, not buried.

### 3.3 Facts separated from inference
Raw evidence, findings, and hypotheses should be visually distinct.

### 3.4 Charts support investigation
Charts are important, but they should support forensic reasoning rather than replace it.

### 3.5 Role-aware simplicity
Different user types need different defaults and complexity levels.
The product should feel approachable to operators and deep enough for investigators.

### 3.6 No dead-end views
A user should be able to move easily between evidence, diagnostics, findings, timeline, charts, and exports without losing context.

---

## 4. User Types

The GUI must support different user types through roles, modes, or configurable defaults.

### 4.1 Quick operator / field user
Needs:
- rapid upload
- simple case creation
- quick health/crash triage
- simple charting
- clear summary
- minimal settings noise

### 4.2 Analyst / engineer
Needs:
- detailed charts
- parse diagnostics
- plugin-level findings
- timeline reconstruction
- parameter and event inspection
- comparison tools

### 4.3 Forensic investigator / incident reviewer
Needs:
- evidence integrity visibility
- provenance and audit trail
- contradiction and hypothesis view
- strong export and replay controls
- structured forensic workflow

### 4.4 Executive / program lead
Needs:
- concise summary
- mission outcome view
- confidence/risk summary
- anomaly/crash summary
- high-level decision support

### 4.5 Admin / enterprise operator
Needs:
- policy controls
- plugin trust management
- user/role configuration
- retention and storage configuration
- audit oversight
- deployment mode control

---

## 5. Required Top-Level Navigation

Recommended top-level navigation:
- Dashboard
- Cases
- Evidence
- Analysis
- Findings
- Timeline
- Reports / Exports
- Settings / Policies
- Admin

The exact labels can change, but these functional areas must exist.

---

## 6. Required Screens

### 6.1 Dashboard
Purpose:
- landing view for recent activity and quick actions

Should show:
- recent/open cases
- recent analyses
- parse failures or warnings
- recent uploads
- shortcuts based on user role
- system notices relevant to mode or trust state

### 6.2 Cases View
Purpose:
- browse and manage investigations

Should show:
- case list
- status
- last analysis time
- evidence count
- severity indicators
- filters and search

### 6.3 Case Workspace
Purpose:
- central hub for one investigation

Should show:
- case metadata
- case status
- evidence inventory
- analysis runs
- current findings summary
- notes / tags
- quick navigation to diagnostics, timeline, charts, and reports

### 6.4 Evidence View
Purpose:
- manage and inspect evidence

Should show:
- evidence items
- hashes
- acquisition metadata
- file type and parser eligibility
- immutable original markers
- derived artifact links
- evidence-related audit trail

### 6.5 Parse Diagnostics View
Purpose:
- expose parser behavior and data quality

Should show:
- parser selected
- parser version
- detected format
- format confidence
- parser confidence
- warnings and errors
- missing topics/streams
- corruption or dropout windows
- timebase anomalies
- stream coverage summary

### 6.6 Analysis View
Purpose:
- run and configure analysis

Should show:
- available analyzers/plugins
- enabled/disabled state
- version and trust state
- required/optional streams
- execution controls
- ruleset selection
- run history

### 6.7 Findings View
Purpose:
- review structured outputs

Should show:
- finding title
- severity
- confidence
- description
- supporting evidence references
- contradicting evidence
- plugin provenance
- links to related charts and timeline windows

### 6.8 Timeline View
Purpose:
- reconstruct events in sequence

Should show:
- phases of flight
- mode changes
- faults and failsafes
- important events
- evidence-linked findings over time
- jump links into chart windows

### 6.9 Charting Workspace
Purpose:
- detailed signal and telemetry investigation

Should show:
- synchronized multi-series charts
- selected channels/streams
- overlays for events and findings
- selectable time windows
- saved views or presets
- comparison tools

### 6.10 Hypothesis View
Purpose:
- evaluate root-cause candidates

Should show:
- candidate hypotheses
- supporting findings
- contradicting findings
- confidence
- unresolved questions
- analyst notes if enabled

### 6.11 Reports / Exports View
Purpose:
- generate and retrieve outputs

Should show:
- JSON case export
- structured report objects
- mission/anomaly/crash report options
- replay package creation
- export history

### 6.12 Settings / Policies View
Purpose:
- configure behavior

Should show:
- local vs connected mode settings
- telemetry opt-in settings
- retention and storage policy
- plugin policy settings
- privacy/export controls
- role defaults

### 6.13 Admin View
Purpose:
- system administration

Should show:
- user roles
- plugin trust inventory
- policy state
- audit logs
- storage status
- deployment mode

---

## 7. GUI Workflow Details

### 7.1 Case creation flow
The user should be able to create a case with minimal friction.
Optional metadata can be collected at creation or later.

### 7.2 Evidence ingest flow
The user should upload one or more files into a case.
The UI should immediately surface:
- file metadata
- hash status
- integrity indicators
- parser eligibility

### 7.3 Parse flow
The parse step should feel explicit.
The user should see when parsing starts, what parser was selected, and what diagnostics were produced.

### 7.4 Analysis flow
The user should be able to run default analysis or a more advanced configured run.
For many users, the default path should be one click.
Advanced users should be able to inspect enabled analyzers and trust states.

### 7.5 Investigation flow
From findings, the user should be able to jump to:
- the relevant timeline window
- the supporting chart region
- the evidence references
- the plugin/analyzer that produced the finding

### 7.6 Export flow
The export flow should be case-based.
The user should understand what is being exported and whether it includes replay artifacts, structured findings, or summary reports.

---

## 8. Deployment Modes

The GUI must adapt based on deployment mode without requiring a totally separate app.

### 8.1 Local Solo Mode
- local-first workflow
- sync disabled by default
- minimal admin complexity

### 8.2 Connected Team / Portal Mode
- explicit upload and sync capabilities
- optional telemetry sharing
- collaboration/project features later
- still based on the same case model

### 8.3 Controlled Enterprise Mode
- stronger policy surfaces
- role restrictions
- plugin trust controls
- retention and audit emphasis

### 8.4 Future Hardened / Isolated Mode
- no required network features
- stricter trust enforcement
- more limited settings and update paths

---

## 9. GUI Requirements for Findings and Charts

Claude must make sure the GUI ties findings to evidence and charts cleanly.

### Required behavior
- every important finding should link to evidence references
- users should be able to jump from a finding to the relevant chart time range
- users should be able to jump from a timeline marker to the related findings
- charts should support overlays for events, anomalies, and phases
- users should be able to compare signals when testing a hypothesis

---

## 10. GUI Requirements for Reporting

The GUI must support both technical and non-technical consumers.

### Technical outputs
- machine-readable JSON case bundle
- parse diagnostics view/export
- findings and evidence references
- replay verification

### Higher-level outputs
- mission summary
- anomaly summary
- crash / mishap summary
- executive summary view

These should be generated from the same underlying case data.

---

## 11. GUI Acceptance Criteria

### Milestone G1
A user can create a case, ingest evidence, run parse, run analysis, inspect findings, inspect charts, and export a case bundle entirely from the GUI.

### Milestone G2
A user can clearly see parser diagnostics, confidence, warnings, missing data, and corruption indicators from the GUI.

### Milestone G3
At least three user types have distinct default experiences:
- quick operator
- analyst/investigator
- admin

### Milestone G4
Users can move naturally between findings, timeline, charts, diagnostics, and reports without leaving the case context.

---

## 12. Final Instruction to Claude

Do not treat the GUI as polish added later.
The GUI is how most people will experience Goose.
It must reflect the forensic model clearly, support different user types, and make evidence-backed investigation feel natural.
