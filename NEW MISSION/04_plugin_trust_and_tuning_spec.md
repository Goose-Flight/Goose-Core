# Goose Claude Pack 04 - Plugin Trust and Tuning Spec

## Purpose

This document defines how Goose plugins must work.
It covers plugin architecture, trust and signing support, policy modes, GUI plugin management, and the future tuning/feedback loop needed for a top-tier open-source flight forensic platform.

Claude should use this as the authoritative specification for the plugin subsystem.

---

## 1. Plugin System Goal

The plugin system is one of Goose’s core strategic advantages.
It must allow Goose to expand analysis coverage rapidly while remaining trustworthy enough for serious forensic and enterprise use.

That means Goose needs both:
- open extensibility for community and ecosystem growth
- strong trust controls for managed, enterprise, and future hardened deployments

Plugins must not be treated as loose scripts.
They are formal analyzers within the forensic engine.

---

## 2. How Plugins Fit Into the Forensic Flow

Plugins operate after evidence has been ingested and parsed.

The intended flow is:
1. case is created
2. evidence is ingested and hashed
3. parser creates canonical flight data + diagnostics + provenance
4. analysis engine selects plugins based on compatibility and policy
5. plugins execute deterministically on canonical data
6. plugins emit findings, diagnostics, and evidence references
7. analysis engine correlates findings into hypotheses and timeline artifacts

Plugins do not parse raw files directly.
Plugins operate on canonical data structures.

---

## 3. Plugin Categories

Claude should support explicit plugin categories such as:
- health / data quality
- crash / mishap
- flight dynamics
- navigation / GPS / EKF
- propulsion / power
- RF / RC / comms
- mission rules / policy
- reporting / enrichment

These categories should be visible in the GUI and available for filtering or policy management.

---

## 4. Plugin Manifest Requirements

Every plugin must have a formal manifest or metadata definition.

### Required plugin metadata
- plugin_id
- name
- version
- author or source
- description
- category
- supported log / vehicle types
- required streams/topics
- optional streams/topics
- configuration schema
- output finding types
- minimum Goose contract version
- plugin type: built-in, local custom, community, enterprise-managed
- trust metadata fields

### Trust metadata support
The metadata model must support:
- hash/fingerprint
- signature field or signature reference
- signer identity if applicable
- source package reference
- trust state

---

## 5. Plugin Contract

Every plugin must:
- accept canonical forensic models only
- be deterministic
- fail gracefully with diagnostics if required data is missing
- emit findings with evidence references
- emit confidence information tied to evidence quality
- record its version and configuration in execution outputs
- avoid hidden global state

### Plugin output contract
Each plugin should return structured results such as:
- findings[]
- plugin_diagnostics
- confidence_notes
- contradiction_flags if relevant
- execution_metadata

---

## 6. Plugin Trust Model

Claude must build Goose with a real plugin trust model from the start.

### Minimum trust states
- built-in trusted
- local unsigned
- local signed
- community installed
- enterprise-managed trusted
- blocked / untrusted

### Product rule
A user must never be confused about:
- which plugins ran
- which plugins were blocked
- why a plugin was allowed or denied
- what version produced a finding
- whether the plugin was trusted, unsigned, or enterprise-approved

---

## 7. Signature and Verification Support

Goose should support plugin signing or at minimum a clean architectural path for it immediately.

### Required design support now
- plugin manifest format
- plugin hashing/fingerprinting
- trust-policy engine
- allowlist support
- verification hook in plugin loading
- GUI visibility of trust state

### Early implementation path
It is acceptable for the first version to include:
- plugin hash/fingerprint tracking
- trust manifest / allowlist verification
- placeholder verification interface for future cryptographic signing

However, the design must not block real signature verification.
Preferably, signature verification should be implemented early for built-in and enterprise-managed plugins.

---

## 8. Deployment-Mode Plugin Behavior

### 8.1 Open-source / community mode
- unsigned plugins may be allowed with warnings
- community plugins may be installed intentionally
- trust state must be visible

### 8.2 Local professional mode
- unsigned local plugins may be allowed by policy
- trust state and source must still be visible

### 8.3 Controlled enterprise mode
- allowlist-based loading
- signed or explicitly trusted plugins only
- plugin version pinning supported
- execution must be auditable

### 8.4 Future hardened / isolated mode
- signed and allowlisted plugins only
- no dynamic remote fetch
- local verification only
- stricter enforcement

---

## 9. GUI Requirements for Plugin Management

Because the web GUI is the main product surface, plugin management must exist there.

### GUI must provide
- plugin inventory list
- plugin category filtering
- version display
- source display
- trust state display
- enabled / disabled state
- compatibility information
- warnings for unsigned or blocked plugins
- policy restrictions by deployment mode

### GUI must also show
- which plugins ran in a given analysis
- which plugins were skipped
- why a plugin was skipped or blocked
- which findings came from which plugin version

---

## 10. Plugin Tuning Framework

Claude must not stop at static plugins.
Goose needs a tuning framework so plugins can improve over time while remaining structured and auditable.

### Tuning goals
- improve threshold quality
- improve confidence scoring
- improve correlation logic
- reduce false positives
- reduce false negatives
- support environment or platform-specific tuning later

### Tuning rule
Tuning must be structured, versioned, and auditable.
Do not let “tuning” become random manual edits to hidden thresholds.

### Tuning model requirements
Goose should support:
- versioned plugin configs
- versioned threshold profiles
- named tuning profiles
- platform- or vehicle-class-specific parameter sets
- test corpus evaluation against tuning changes
- rollback to prior tuning profiles

### Tuning provenance
Every analysis should record:
- plugin version
- active tuning profile
- threshold/config version
- any non-default settings applied

---

## 11. Plugin Feedback and Learning Loop

Goose should eventually support a product feedback loop without corrupting the evidentiary core.

### Future feedback loop can include
- opt-in upload of anonymized findings or telemetry slices
- benchmark comparisons
- plugin effectiveness review
- false positive / false negative tracking
- tuning recommendations

### Critical rule
Feedback loops must remain separate from the evidentiary core.
No cloud feedback system should silently alter local forensic truth.
Changes must flow through explicit versioned plugin or tuning updates.

---

## 12. Plugin Development Model

Claude should support a clean plugin development experience.

### Plugin developers should have
- clear plugin contract
- clear manifest format
- example plugins
- validation tooling
- compatibility checks
- tests against canonical data fixtures

### Goose should provide
- built-in plugin examples
- plugin validation hooks
- plugin diagnostics schema
- compatibility metadata checks

This helps Goose become a real open-source ecosystem rather than a closed core with random extensions.

---

## 13. Acceptance Criteria for Plugin Subsystem

### Plugin Milestone P1
Plugins have formal metadata and a clear contract.

### Plugin Milestone P2
The analysis engine records which plugin version and configuration produced each finding.

### Plugin Milestone P3
The GUI shows plugin inventory, trust state, and execution results.

### Plugin Milestone P4
The system supports hash/fingerprint tracking and policy-based plugin trust decisions.

### Plugin Milestone P5
Goose supports versioned tuning profiles and records them in analysis outputs.

---

## 14. Final Instruction to Claude

Build the plugin system as a first-class part of the forensic platform.
It must be extensible enough for open-source growth, structured enough for tuning and benchmarking, and trustworthy enough to support serious controlled deployments later.
