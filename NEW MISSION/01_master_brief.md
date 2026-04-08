# Goose Claude Pack 01 - Master Brief

## Purpose

This is the top-level execution brief for Claude.
It defines what Goose is, what it must become, and what architectural rules must govern all implementation.

Claude should read this document first.
All other Goose Claude Pack documents are subordinate to this one.

---

## Product Mission

Goose is being built into a **top-tier open-source flight forensic platform** for UAV and autonomous flight log investigation.

The product must become credible for:
- serious crash investigation
- incident and anomaly analysis
- flight health analysis
- mission reconstruction
- evidence-backed root-cause analysis
- future enterprise and government use

The open-source version should establish technical credibility and community momentum.
The underlying architecture must be strong enough that Goose can later support:
- local professional deployments
- cloud-connected portal workflows
- enterprise server deployments
- controlled or future hardened deployments

---

## What Goose Is

Goose is:
- a **local-first forensic engine** for flight log analysis
- a **case-oriented investigation system**
- a **plugin-driven analysis platform** built on canonical parsed data
- a **GUI-first product** with CLI support for automation and admin workflows
- a system that must preserve evidence integrity, expose uncertainty, and support replay

Goose is not:
- a generic robotics analytics dashboard
- an LLM-only explanation layer
- a cloud-only log viewer
- a collection of ad hoc scripts
- a demo UI sitting on top of fragile internals

---

## Core Product Principles

### 1. Forensic integrity first
Original evidence must be preserved.
Every major conclusion must be traceable.
Findings must cite supporting evidence.

### 2. Local-first core
The critical analysis path must run locally.
Networked features are allowed, but they must be optional layers on top of the forensic core.

### 3. GUI first
The web GUI is the main product surface.
Anything important must be operable through the GUI.
The CLI exists for automation, scripting, testing, and admin workflows.

### 4. Deterministic analysis
Given the same evidence, rules, and plugin versions, the system should produce reproducible outputs.

### 5. Explicit uncertainty
Parser ambiguity, missing streams, corruption, contradictory indicators, and low-confidence conclusions must be surfaced, not hidden.

### 6. Plugin extensibility with trust controls
Goose must be open and extensible, but also capable of trust controls such as allowlists, signatures, and policy-driven plugin enforcement.

### 7. One core engine
Local app, future portal, and future enterprise offerings must all use the same core forensic case model and analysis engine.
Do not build separate logic paths that bypass the core.

### 8. No LLM in the evidentiary core
LLMs may later help summarize findings or guide users, but they must not be the source of truth for evidence handling, parsing, findings, or root-cause logic.

---

## Primary Build Goal

The foundational sprints must produce a real forensic substrate.

By the end of the foundational work, Goose must be able to:
- create a case
- ingest evidence immutably
- hash and manifest the evidence
- parse a real log with diagnostics
- run deterministic analyzers/plugins
- produce evidence-linked findings and hypotheses
- show results in the GUI
- export a replayable case bundle
- replay the case later with reproducible results

---

## High-Level Product Layers

### Layer 1: Core forensic engine
- case model
- evidence ingest
- parser framework
- canonical data model
- analysis engine
- plugin framework
- findings and hypotheses
- export and replay
- audit trail

### Layer 2: GUI application
- case workflow
- evidence and diagnostics views
- charts and timeline
- findings review
- plugin controls
- reports and export
- role-aware UX

### Layer 3: Connected portal features
- explicit uploads
- optional telemetry sharing
- benchmarking
- tuning feedback loops
- fleet/project views
- collaboration

### Layer 4: Future enterprise / hardened controls
- stricter trust policies
- signed plugins
- offline controls
- deployment policies
- audit and retention enforcement

---

## Non-Negotiable Rules

Claude must not:
- keep ad hoc temp-file ingestion as the core workflow
- build GUI-only logic that bypasses the forensic engine
- build cloud-only analysis separate from local core logic
- pretend unsupported parsers are implemented
- allow findings without evidence references
- hide parser failures or corruption
- make the GUI a shell while the CLI is the real product
- let LLMs decide forensic truth

---

## Document Map

Claude must use the full Goose Claude Pack:

1. **Master Brief**
2. **Forensic Core Architecture Spec**
3. **GUI and Workflow Spec**
4. **Plugin, Trust, and Tuning Spec**
5. **Sprint Plan and Acceptance Criteria**

Claude should use all of them together.
If there is conflict, this Master Brief takes priority.

---

## Final Instruction to Claude

Build Goose as if it will later be examined by a skeptical enterprise or government evaluator.

That means the product must feel:
- structured
- trustworthy
- replayable
- explainable
- auditable
- extensible
- GUI-driven
- grounded in evidence

Do not optimize for flash.
Optimize for durable architecture.
