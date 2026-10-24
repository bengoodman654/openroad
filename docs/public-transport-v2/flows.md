# Public Transport v2.2 - corrected core workflow diagrams

These Mermaid diagrams summarise the normative v2.2 contract. The downloadable design package contains the **full editable SVG and Graphviz versions**, 28-finding traceability register, complete v2.1 audit, and 105-row acceptance matrix. Earlier flowcharts are superseded where inconsistent.

## 01. Master and proven coverage
```mermaid
flowchart TD
 A[Choose journey / service / departures / map] --> B[Resolve intended place - explicit before GPS]
 B --> C{Licensed and validated capability for area/mode/date?}
 C -- Yes --> D[Pin immutable timetable snapshot]
 C -- No --> E{Compatible previous snapshot?}
 E -- Yes --> F[Label age and limitations] --> D
 E -- No --> G[COVERAGE_MISSING and external preparation]
 D --> H[Run independent task engine]
 H --> I[Typed result and next actions]
 I --> J[Optional enrichment without swapping identity]
```

## 02. Feasible journeys
```mermaid
flowchart TD
 A[Origin / destination / depart-after or arrive-by] --> B{Complete snapshot and graph coverage?}
 B -- No --> C[COVERAGE_MISSING]
 B -- Yes --> D[Validate service day, timezone, DST and calendar]
 D --> E[Search direct/transfers and pedestrian connectors]
 E --> F{Complete hard-constraint-valid itinerary?}
 F -- No --> G[NO_JOURNEY - explain binding constraint]
 F -- Yes --> H[Rank up to three distinct useful journeys]
 H --> I[Keep immutable itinerary ID and user selection]
 I --> J[Enrich only; confirm if disruption requires guidance change]
```

## 03. Services and departure boards
```mermaid
flowchart TD
 A[Service number/name or stop identity] --> B[Choose explicit geography / operator]
 B --> C{Indexed schedule coverage exists?}
 C -- No --> D[COVERAGE_MISSING]
 C -- Yes --> E[Match namespaced line/operator/pattern IDs]
 E --> F{Matches?}
 F -- None --> G[NO_MATCH]
 F -- One or more --> H[Select service variant, direction and stop]
 H --> I[Show ordered published route even when not operating today]
 I --> J{Operating on chosen date?}
 J -- Yes --> K[Scheduled/predicted/cancelled board]
 J -- No --> L[Known service; no scheduled runs that day]
```

## 04. Live data
```mermaid
flowchart TD
 A[Show valid scheduled baseline] --> B{Live fetch allowed by provider and host budgets?}
 B -- No --> C[Use timestamped cache or scheduled-only]
 B -- Yes --> D[Deduplicated bounded provider call]
 D --> E{Trip-occurrence match trustworthy?}
 E -- No --> F[Route-only vehicle, never a trip ETA]
 E -- Yes --> G[Fresh observed or predicted overlay]
 F --> H{Verified disruption for the selected service?}
 G --> H
 C --> H
 H -- Yes --> I[Make cancelled leg unusable; offer replan and confirmation]
 H -- No --> J[Keep valid schedule and selected trip]
```

## 05. Data preparation and hosting
```mermaid
flowchart TD
 A[Licensed source register] --> B[Off-host build and normalise]
 B --> C{Semantic validation and golden fixtures pass?}
 C -- No --> D[Quarantine; keep existing active snapshot]
 C -- Yes --> E[Immutable versioned package + manifest]
 E --> F{Measured JustHostMe serving budget passed?}
 F -- No --> D
 F -- Yes --> G[Stage and integrity-check upload]
 G --> H[Atomic pointer swap + retain old in-flight snapshots]
 H --> I{Post-publish canary cases pass?}
 I -- No --> J[Rollback]
 I -- Yes --> K[Bounded read-only query serving]
```

## 06. Persistent Back and X + cancellation
```mermaid
flowchart TD
 A[Back arrow LEFT and X RIGHT in main Where to field] --> B{Back or X?}
 B -- Back --> C[Pop one view; prompt before discarding dirty edit]
 C --> D[Stop view-owned children only; keep guidance]
 B -- X --> E{Dirty edit?}
 E -- Yes --> F[Confirm discard or keep editing]
 E -- No --> G{Visible foreground task?}
 G -- Yes --> H[Cancel locally immediately and invalidate generation]
 H --> I[Authenticated remote cancellation; lease / timeout]
 I --> J[Detach shared work; reject all late replies]
 G -- No --> K{Viewing active guidance?}
 K -- Yes --> L[Confirm Stop guidance]
 K -- No --> M{Idle selected PT result?}
 M -- Yes --> N[Close selection]
 M -- No --> O[X visible but disabled at PT root]
```

## 07. Recovery and scoped release gates
```mermaid
flowchart TD
 A[Typed query + trace ID] --> B{Verified capabilities and data?}
 B -- No --> C{Compatible fallback snapshot?}
 C -- Yes --> D[Label age and limitations]
 C -- No --> E[Explain coverage gap; do not foreground-import]
 B -- Yes --> F[Search feasible itinerary / service]
 D --> F
 F --> G{Feasible?}
 G -- No --> H[NO_MATCH or NO_JOURNEY with specific retry]
 G -- Yes --> I[Stable scheduled result + optional live layer]
 H --> J[Run release-scoped integration tests and measured host checks]
 I --> J
 E --> J
 J --> K{P0, security, licence and host gates all evidenced?}
 K -- Yes --> L[Scoped pilot with rollback - not unverified UK-wide claim]
 K -- No --> M[BLOCK release; keep current working app]
```

**Evidence disclaimer:** Green GitHub reference-test results do **not** mark Android/server end-to-end acceptance complete. All 105 production acceptance tests still require fixtures and real integration evidence.
