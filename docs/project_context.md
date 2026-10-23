# V0 LEO-PNT Mission-Analysis Foundation
## Project Context and Development Guardrails for Antigravity

**Document purpose:** Provide stable background context for AI-assisted development of the V0 proof of concept. Read this document before undertaking any implementation task.

**Status:** Working development context, 23 October 2026  
**Scope:** Generic, pre-contract V0 foundation only  
**Development approach:** Human-led engineering with AI-assisted implementation. Work in small, testable increments. Do not attempt to generate the complete tool in one task.

---

# 1. Wider programme context

A future LEO-PNT project requires an end-to-end model for assessing the dissemination of data through a LEO satellite and ground network. The expected contractual tool will support Phase A/B1 architecture assessment by modelling how data can move from defined sources, through space and ground network elements, to the applicable destination or service endpoint.

The complete future model is expected to combine:

1. mission and constellation definition;
2. orbit propagation and ephemeris generation;
3. satellite-to-ground and inter-satellite geometric access;
4. communications-link opportunities and usable contact plans;
5. time-dependent network topology;
6. routing and resource allocation;
7. traffic generation, storage, queueing and transmission;
8. failures and degraded scenarios; and
9. end-to-end performance indicators and statistical analysis.

The project contract is not yet active. A simplified, general-purpose precursor is therefore being developed as **V0**. V0 is intended to establish reusable company background IP, reduce technical risk, and provide a mission-analysis foundation that can later be adapted to the customer-specific LEO-PNT work.

V0 must remain generic. Do not insert customer-specific requirements, data, documents, architecture, ground-station information or proprietary G2G source code into the V0 repository.

---

# 2. Development principles

The following principles apply throughout development:

- **Keep V0 shallow and achievable.** Approximately 1.5 to 2 months and just under 1 FTE are available.
- **Use proven libraries wherever practical.** Do not implement orbital mechanics, reference-frame transformations or general event-detection algorithms from first principles without a demonstrated need.
- **Preserve modularity at important boundaries.** Configuration, propagation, geometry, results and export should be separable, but V0 must not become a large abstract framework.
- **Keep library-specific types inside adapters or calculation modules.** Scenario definitions and exported analysis products should not expose Skyfield or SGP4 implementation objects.
- **Prioritise correctness, traceability and reproducibility over breadth or presentation.**
- **Use analytical propagation only in V0.** Numerical integration, manoeuvres and selectable force models are excluded.
- **Use access opportunities, not operational contacts, as the V0 geometry product.** Geometric access does not imply communications availability, scheduling or successful data transfer.
- **Develop through small issues.** Each issue should have explicit inputs, outputs, exclusions and tests.
- **Review every AI-generated diff.** Code is not accepted merely because it executes.
- **Do not invent validation truth.** Independently verified values, logical invariants and internally generated regression data must be clearly distinguished.

---

# 3. Version roadmap

## 3.1 V0: mission-analysis foundation

V0 is an internal, generic precursor. It should demonstrate a complete and reproducible mission-analysis workflow without implementing the dissemination network itself.

### V0 architectural blocks

#### A. Execution and Scenario Configuration

Responsibilities:

- command-line execution;
- YAML scenario loading;
- schema validation;
- definition of the analysis period;
- Walker constellation parameters;
- fixed ground-station definitions;
- minimum-elevation constraints;
- propagation/output interval; and
- requested output products.

#### B. Library Adapter and Environment Setup

Responsibilities:

- conversion of validated configuration into calculation inputs;
- Walker/design-element generation;
- construction of SGP4 `Satrec` records;
- construction of `SatrecArray` for accelerated batch propagation;
- Skyfield timescale and coordinate setup;
- explicit propagation assumptions and constants; and
- confirmation that compiled SGP4 acceleration is active.

Use a lightweight adapter. Do not create a generic plugin architecture or internal equivalents for every library object.

#### C. Propagation and Ephemeris

Responsibilities:

- analytical SGP4 propagation only;
- common configurable time grid;
- batched TEME position and velocity states;
- retention and inspection of SGP4 error codes;
- standard ephemeris product; and
- execution-time measurement.

#### D. Geometry and Access

Responsibilities:

- fixed ground-station geometry;
- minimum-elevation access;
- Skyfield event detection where practical;
- construction of access-window records; and
- optional, simple neighbour-based ISL visibility only if core scope is complete.

All-pairs ISL analysis is excluded from committed V0 scope.

#### E. Standard Mission-Analysis Results and Summary Metrics

Responsibilities:

- ephemeris products;
- access-window records;
- per-pair access summaries;
- per-ground-station summaries;
- scenario-level diagnostic metrics; and
- traceability from summary metrics to raw access windows.

#### F. Export and Diagnostic Visualisation

Responsibilities:

- CSV and JSON export;
- validated scenario snapshot;
- run manifest;
- log output;
- a small number of diagnostic plots; and
- no interactive GUI or dashboard.

### V0 cross-cutting services

- units and conventions;
- logging and error handling;
- run provenance;
- automated tests;
- dependency and third-party licence records.

Generic caching, a reporting engine and a verification-management framework are not V0 deliverables.

### Equivalent G2G reference component

V0 aligns mainly with the generalised **G2G Orbit Propagator Tool** and its functions for scenario definition, input validation, orbit initialisation, propagation, time/frame handling, visibility/access calculation, structured export and diagnostics.

G2G is a reference, not a design to copy. V0 deliberately consolidates those functions into fewer modules because of the available effort.

---

## 3.2 V1: initial dissemination capability

V1 is expected to be the first customer-specific contractual release. It should build directly on V0 rather than replace it.

### V1 evolution

#### Existing V0 blocks expanded

- Scenario configuration gains node roles, link types, data source/destination, simple traffic definitions and routing settings.
- Mission geometry gains constrained neighbour-based ISL opportunities and directional source/destination definitions.
- Export gains contact, route and initial delivery products.

#### New V1 downstream blocks

##### A. Contact Construction and Simple Resource Model

Convert geometric access opportunities into usable contacts using simplified assumptions such as:

- minimum contact duration;
- acquisition/release margin;
- nominal data rate or capacity;
- propagation delay;
- basic ground-station availability;
- finite simultaneous links where required; and
- one deterministic conflict-resolution rule.

This block must preserve the distinction between geometric access and allocated/usable contact.

##### B. Initial Network and Route Selection

Provide:

- network nodes and time-dependent edges;
- direct-path routing;
- one basic graph-based method, such as shortest path or earliest arrival; and
- route-plan records.

##### C. Simplified Data-Product Transfer

Model a generic data product with:

- identifier;
- generation time;
- source and destination;
- data volume;
- priority or deadline if required; and
- delivered, failed or pending status.

V1 should demonstrate movement of data over selected contacts without introducing packet-level protocol fidelity.

##### D. Initial Results and KPI Module

Provide selected early measures such as:

- selected route;
- time to first opportunity;
- end-to-end delivery latency;
- delivery success;
- contact use; and
- simple capacity/throughput summaries.

### Equivalent G2G reference components

V1 aligns mainly with a reduced form of the generalised **G2G Contact Plan Generation Tool**, plus a thin subset of the **G2G Ground-Based Mission-Data Uplink Simulation** needed to demonstrate a first end-to-end data transfer.

V1 should not imply that the complete G2G-style contact-allocation optimiser, packetisation, acknowledgement handling or resource scheduler is already implemented.

---

## 3.3 V2: functionally complete dissemination baseline

V2 should mature and separate the V1 functions into a complete, verified Phase A/B1 assessment baseline.

### V2 architectural blocks

#### A. System and Scenario Configuration

Modular configuration sections for:

- mission and constellation;
- ground segment;
- communications links;
- resources;
- network policies;
- traffic/services;
- failures and degraded cases;
- analysis settings; and
- outputs.

#### B. Mission Geometry Module

Mature V0/V1 capability for:

- SGP4 propagation and batched states;
- optional imported ephemerides;
- ground access;
- constrained ISL opportunities;
- user-defined neighbour/topology rules; and
- agreed geometry constraints.

#### C. Link Performance Module

Convert geometry into link properties using either parameterised or detailed models:

- availability;
- capacity/data rate;
- propagation delay;
- setup/acquisition time;
- asymmetry;
- minimum usable duration; and
- operational constraints.

#### D. Contact Planning and Resource Allocation

Provide:

- directional time-dependent contacts;
- finite antenna/terminal resources where required;
- competing access opportunities;
- priorities;
- continuity or gap objectives;
- nominal and degraded contact plans; and
- validation of overlaps and resource conflicts.

#### E. Time-Dependent Network, Routing and Scheduling

Provide the agreed routing methods, potentially including:

- direct delivery;
- shortest path;
- earliest arrival;
- minimum hop;
- capacity-aware routing;
- contact-graph routing;
- route recalculation following failures; and
- resource-aware scheduling.

Only methods required for the architecture trades should be implemented.

#### F. Traffic and Dissemination Simulation

Provide:

- data generation;
- sources and destinations;
- priorities/deadlines;
- queueing and storage;
- processing delay;
- transmission and capacity consumption;
- failed or expired delivery;
- link and node failures; and
- recovery scenarios.

Use message/data-product or data-volume level unless packet-level modelling is shown to affect the required decisions.

#### G. End-to-End KPI and Analysis Module

Provide agreed measures such as:

- end-to-end latency;
- latency percentiles;
- delivery success;
- throughput;
- capacity utilisation;
- availability and continuity;
- queueing delay;
- storage occupancy;
- delivery within deadline; and
- scenario comparison.

Every KPI should remain traceable to lower-level contacts, routes and delivery events.

#### H. Export, Visualisation and Reporting

Provide:

- contact plans;
- network/topology products;
- route traces;
- transmission/delivery histories;
- KPI distributions;
- scenario comparisons;
- run manifests; and
- technical-report evidence.

### Equivalent G2G reference components

V2 aligns with the complete generalised chain comprising:

- **G2G Orbit Propagator Tool**;
- **G2G Contact Plan Generation Tool**;
- **G2G Ground-Based Mission-Data Uplink Simulation**; and
- **G2G ISL-Based Network Dissemination Simulation**.

The LEO-PNT implementation may diverge in simulation fidelity, message abstraction, routing methods, resource allocation and tool boundaries. The G2G chain is mainly evidence for separating mission geometry, contacts and dissemination through stable intermediate products.

---

# 4. Key modular interfaces and canonical products

Important module boundaries should use library-independent products.

## 4.1 Validated scenario

Contains:

- scenario and schema identifiers;
- analysis start/end;
- constellation definition;
- ground stations;
- propagation settings;
- access settings; and
- output settings.

## 4.2 Ephemeris product

Contains:

- satellite identifiers;
- timestamps and time scale;
- position and velocity arrays;
- reference frame;
- units;
- propagation error/status information; and
- model metadata.

Expected V0 numerical shape:

- position: `(number_of_satellites, number_of_times, 3)`;
- velocity: `(number_of_satellites, number_of_times, 3)`;
- SGP4 errors: `(number_of_satellites, number_of_times)`.

## 4.3 Access opportunity

Contains:

- scenario and run identifiers;
- source satellite identifier;
- destination ground-station identifier;
- access type;
- start and end UTC;
- duration;
- applied minimum elevation;
- geometry method;
- quality/warning status; and
- provenance.

## 4.4 Later-version products

V1/V2 will add:

- `Contact`;
- `RoutePlan`;
- `DataProduct`;
- `TransmissionEvent`;
- `DeliveryEvent`; and
- `KPIResult`.

Do not implement these in V0 merely to anticipate future scope. Ensure only that V0 products contain stable identifiers and timestamps that can be consumed downstream.

---

# 5. Planned V0 technology stack

## Python

Primary application, orchestration and test language.

## `python-sgp4`

Use as the sole V0 analytical propagator.

Planned use:

- construct SGP4 `Satrec` records;
- use compiled C++ acceleration;
- use `SatrecArray` for multiple satellites and times;
- output TEME positions/velocities; and
- inspect all returned error codes.

Do not write custom C++ unless profiling establishes an unmet performance need.

## Skyfield

Planned use:

- time handling;
- wrapping SGP4 records as required;
- coordinate/observer calculations;
- fixed ground-station definitions;
- elevation, azimuth and range; and
- rise/culmination/set event searches.

Start with Skyfield event detection for ground access and benchmark it. If many satellite-station event searches cannot meet the later scale requirement, consider batched sampled geometry as an optimisation. Do not build a general event engine in V0.

## NumPy

Planned use:

- time grids;
- Walker parameter arrays;
- batched positions and velocities;
- SGP4 error screening;
- bulk geometry and masks where needed;
- access statistics; and
- efficient numerical processing.

Use arrays for regular numerical data and typed Python/Pydantic objects for configuration and metadata.

## Pydantic and YAML

Use YAML for human-editable scenarios and a small Pydantic model set for validation.

Expected models:

- `ScenarioConfig`;
- `ConstellationConfig`;
- `GroundStationConfig`;
- `AnalysisConfig`; and
- `OutputConfig`.

## pytest

Use for configuration, constellation, propagation, access, export and end-to-end regression tests.

## Matplotlib

Use only for two or three diagnostic static plots. No dashboard or general plotting framework.

---

# 6. Important modelling assumptions and unresolved points

## 6.1 Synthetic Walker constellation and SGP4

SGP4 uses mean-element inputs. A synthetic Walker constellation defined by altitude, inclination, planes, satellites and phasing cannot be assumed to be an exact conversion from arbitrary osculating Keplerian elements.

For V0:

- use a documented engineering approximation to construct representative SGP4-compatible design records;
- use a common epoch;
- initially use circular or near-circular design orbits;
- initially set `B*` to zero unless a better scenario assumption is agreed;
- explicitly select and record the SGP4 gravity-constant set;
- validate orbital period, altitude behaviour, plane spacing, phasing and access plausibility; and
- describe the output as representative design-orbit geometry, not high-fidelity orbit prediction.

This is a significant modelling decision and must not be hidden inside code.

## 6.2 Ground assets

V0 primarily models fixed ground stations or gateways.

All V0 ground stations may share a common geometric model:

- fixed geodetic location;
- minimum elevation;
- always available;
- no antenna capacity, scheduling, link budget, weather or terrestrial-network effects.

Retain explicit station identifiers and, if useful, a generic asset role field. Do not model end-user service behaviour in V0.

## 6.3 Access versus contact

V0 output is geometric access. It does not establish:

- antenna availability;
- link performance;
- allocated resources;
- usable capacity;
- successful transmission; or
- scheduled contact.

Those distinctions become explicit in V1/V2.

---

# 7. V0 foundational requirements

1. **Configurable scenarios:** The tool shall load externally defined scenarios containing the analysis period, Walker constellation parameters, ground-station locations, minimum elevation, propagation interval and requested outputs.
2. **Constellation generation:** The tool shall generate representative Walker-type constellations with configurable satellite count, plane count, phasing, altitude, inclination and common epoch.
3. **Analytical propagation:** The tool shall propagate configured satellites using accelerated SGP4 and produce time-tagged positions, velocities and error statuses.
4. **Ground access:** The tool shall calculate geometric access windows between configured satellites and fixed ground stations using Earth line of sight and a configurable minimum-elevation constraint.
5. **Scalability:** The mature V0 shall support an agreed reference case with at least 100 satellites and multiple ground stations on standard business hardware in minutes rather than hours.
6. **Standard products:** The tool shall produce machine-readable ephemeris, access-window and summary products with identifiers, timestamps, frames, units and modelling metadata.
7. **Basic metrics:** The tool shall calculate access counts, durations, gaps/revisit intervals and ground-station access coverage summaries.
8. **Reproducibility:** Each execution shall record the validated configuration, software/dependency versions, model settings, errors, warnings and generated files.
9. **Modularity and verification:** Configuration, propagation, geometry, result processing and export shall have documented boundaries and automated tests.
10. **IP/dependency control:** All third-party software and data shall be recorded by component, version, source, licence and modification status.

---

# 8. Proof-of-concept development roadmap

Development progresses through three scenarios. These stages add scale gradually and should not add unrelated capability.

## Stage 1: smoke test

### Purpose

Prove that the development environment and principal libraries are connected correctly.

### Scope

- one synthetic satellite;
- one fixed ground station;
- six-hour analysis;
- coarse five-minute ephemeris interval initially;
- one SGP4 record;
- one propagated state series;
- one ground-access calculation;
- one access-window export; and
- minimal logging.

### Expected workflow

```text
Load a very small scenario
→ construct one SGP4 satellite
→ propagate it
→ check SGP4 errors
→ calculate access to one station
→ export access windows
```

### Stage 1 completion criteria

- the environment installs reproducibly;
- compiled SGP4 acceleration is reported;
- valid states are produced for all requested times;
- no unexplained SGP4 error occurs;
- zero or more access windows are returned without failure;
- every returned window has positive duration and lies inside the analysis interval;
- one command or test executes the smoke flow; and
- at least a few focused unit tests pass.

Stage 1 is a developer smoke case, not the final architecture demonstration.

---

## Stage 2: full POC-01 reference scenario

### Objective

Demonstrate the complete V0 vertical workflow with a scenario small enough for manual inspection.

### Constellation

- Walker delta 6/2/1;
- six satellites;
- two orbital planes;
- three satellites per plane;
- altitude: 550 km;
- inclination: 53 degrees;
- circular or near-circular representative design orbit;
- RAAN origin: 0 degrees;
- common fixed UTC epoch;
- initial `B*`: 0;
- analytical SGP4 propagation only; and
- no manoeuvres.

### Ground stations

Use two generic fixed stations:

1. `GS-EQUATOR`
   - latitude: 0 degrees;
   - longitude: 0 degrees;
   - altitude: 0 m;
   - minimum elevation: 10 degrees.

2. `GS-MIDLAT`
   - latitude: approximately 52 degrees;
   - longitude: approximately 4 degrees;
   - altitude: 0 m;
   - minimum elevation: 10 degrees.

Use generic identifiers and synthetic/public coordinates only.

### Analysis settings

- duration: 24 hours;
- batched ephemeris interval: 60 seconds;
- input/output time scale: UTC at external boundaries;
- raw SGP4 output frame: TEME;
- access method: Skyfield event detection initially;
- one CLI command from a YAML scenario.

### Mandatory POC-01 functions

#### Configuration and validation

Validate:

- positive satellite and plane counts;
- satellite count divisible by plane count;
- valid altitude and inclination;
- valid latitude/longitude;
- valid elevation mask;
- unique identifiers;
- end after start; and
- positive analysis timestep.

#### Walker generation

Produce:

- satellite identifier;
- plane and slot number;
- RAAN;
- mean-anomaly/phasing value;
- inclination;
- mean-motion/design inputs; and
- all assumptions required to initialise SGP4.

#### Batched SGP4 propagation

Produce:

- common time grid;
- `SatrecArray` batch;
- position and velocity arrays;
- SGP4 error matrix;
- execution timing; and
- warnings/errors.

#### Ground-access analysis

For each satellite-station pair, calculate:

- access start;
- access end;
- duration;
- culmination time where readily available; and
- maximum elevation where readily available without disproportionate complexity.

#### Basic metrics

Per satellite-station pair:

- count of access windows;
- total access duration;
- minimum, mean and maximum duration;
- minimum, mean and maximum access gap, where defined.

Per station:

- total number of windows;
- total time with at least one satellite accessible;
- percentage of run with at least one satellite accessible; and
- longest period without access.

Scenario level:

- satellites successfully propagated;
- satellites with and without station access;
- total generated windows; and
- execution time.

### Required outputs

```text
outputs/
├── validated_scenario.json
├── constellation_elements.csv
├── ephemeris_selected_satellite.csv
├── access_windows.csv
├── access_metrics.json
├── run_manifest.json
├── run.log
├── access_timeline.png
└── selected_satellite_diagnostic.png
```

Exporting the complete ephemeris is optional in POC-01. A selected-satellite diagnostic ephemeris is sufficient unless full output is needed for testing.

### Access-window fields

At minimum:

- scenario ID;
- run ID;
- satellite ID;
- ground-station ID;
- start UTC;
- end UTC;
- duration seconds;
- minimum elevation degrees;
- access type;
- geometry method; and
- quality/warning field.

### Run-manifest fields

At minimum:

- scenario ID;
- run ID;
- execution time;
- Git commit/version where available;
- Python version;
- dependency versions;
- SGP4 compiled acceleration status;
- SGP4 constants selection;
- analysis start/end and timestep;
- assumptions;
- warnings/errors; and
- output file list.

### POC-01 acceptance criteria

1. One command executes the complete scenario.
2. Six unique satellites are created in two planes with three slots per plane.
3. All satellites are propagated across the complete analysis period.
4. No unexplained SGP4 error remains.
5. Access windows are generated or a valid no-access result is reported for every pair.
6. Every window has positive duration and lies inside the run period.
7. Windows for the same pair do not overlap.
8. Summary metrics reconcile with raw windows.
9. Repeating the run with identical inputs gives identical deterministic outputs, excluding run timestamp and permitted metadata.
10. The manifest identifies software, dependencies, scenario and calculation settings.
11. At least one access case is manually inspected or compared with an independent reference.
12. Tests for validation, Walker layout, propagation and access logic pass.

---

## Stage 3: scaled performance scenario

### Purpose

Demonstrate that the same architecture scales without adding new model fidelity.

### Initial scale case

- 120 satellites;
- representative Walker plane arrangement;
- five fixed ground stations;
- 24-hour duration;
- 30- or 60-second ephemeris interval;
- same SGP4, Skyfield, result and export interfaces as POC-01.

### Measure

- constellation-generation time;
- SGP4 propagation time;
- coordinate/access calculation time;
- output/serialization time;
- total runtime;
- peak memory;
- number of access windows;
- result-file sizes;
- SGP4 error count; and
- hardware/environment details.

### Stage 3 intent

Stage 3 is a benchmark and scalability test, not a new feature release. Do not add custom C++, multiprocessing, caching or sampled-geometry optimisation until profiling identifies a real bottleneck.

If Skyfield pairwise event searches do not meet the performance objective, evaluate this sequence:

1. confirm the bottleneck through profiling;
2. reduce unnecessary repeated conversions;
3. consider batched sampled geometry using NumPy;
4. process stations or times in chunks to limit memory;
5. optionally refine only threshold crossings;
6. consider additional compiled code only as a last resort.

The exact maximum runtime should be agreed once the reference hardware is available. The intended order of magnitude is minutes, not hours, on a standard business laptop.

---

# 9. Test strategy

## Configuration tests

- accept valid reference scenario;
- reject non-divisible satellite/plane count;
- reject invalid latitude/longitude;
- reject invalid inclination/elevation;
- reject negative or zero duration/timestep;
- reject duplicate identifiers.

## Walker-generation tests

- correct satellite count;
- correct plane and slot count;
- unique identifiers;
- correct RAAN spacing;
- correct documented phasing convention;
- deterministic output from identical inputs.

## Propagation tests

- expected array dimensions;
- valid times across requested interval;
- all SGP4 errors checked;
- approximate radius and period physically plausible;
- deterministic state output;
- clear failure if accelerated implementation is unavailable, if acceleration is mandatory.

## Access tests

- valid zero-access result;
- windows inside analysis limits;
- positive durations;
- no overlap per pair;
- lower elevation mask produces access not less than a higher mask for the same case;
- repeatable output;
- comparison of one case with an independent or manually inspected reference.

## Export tests

- required files produced;
- required fields present;
- units and timestamps explicit;
- JSON can be parsed;
- CSV row count reconciles with result objects;
- manifest contains required provenance.

## End-to-end regression test

Use POC-01 as the primary small regression scenario. Store a carefully reviewed compact expected result or invariant set. Do not use a large generated file as unexplained validation truth.

---

# 10. Explicit V0 exclusions

Do not implement these unless a later task explicitly changes scope:

- numerical propagation;
- selectable force models;
- manoeuvres;
- high-fidelity orbit determination;
- antenna patterns or link budgets;
- weather effects;
- communications capacity modelling;
- ground-station antenna allocation;
- operational contact scheduling;
- all-pairs ISL modelling;
- routing;
- traffic generation;
- data dissemination;
- message packetisation;
- acknowledgements;
- storage/queue simulation;
- failure/recovery simulation;
- interactive GUI;
- web dashboard;
- generic plugin framework;
- generic cache service;
- custom C++ before profiling;
- customer-specific LEO-PNT information.

---

# 11. Proposed repository structure

```text
v0-mission-analysis/
├── README.md
├── pyproject.toml
├── dependency-lock-file
├── THIRD_PARTY_NOTICES.md
├── docs/
│   ├── architecture.md
│   ├── assumptions.md
│   ├── decisions/
│   ├── verification.md
│   └── ai_assistance_log.md
├── scenarios/
│   ├── smoke_01.yaml
│   ├── poc_01.yaml
│   └── scale_01.yaml
├── src/
│   └── v0_tool/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── constellation.py
│       ├── sgp4_adapter.py
│       ├── propagation.py
│       ├── access.py
│       ├── results.py
│       ├── metrics.py
│       ├── export.py
│       └── plotting.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── reference/
│   └── acceptance/
└── outputs/
    └── .gitkeep
```

This is a proposed structure, not a requirement to create every module immediately. Begin with the fewest files needed for Stage 1 and split modules only when responsibilities become clear.

---

# 12. AI-assisted development rules

Before changing code for any task:

1. Read this context file and the relevant issue/task.
2. Inspect the current repository and tests.
3. State the intended files and changes briefly.
4. Identify any ambiguity or assumption that materially changes behaviour.
5. Implement only the requested issue.
6. Add or update focused tests.
7. Run the relevant test suite.
8. Report changed files, tests run, results and unresolved concerns.
9. Do not commit automatically unless explicitly instructed.
10. Do not add dependencies without explaining the purpose and licence implications.

When generating code:

- prefer simple, readable functions;
- use type hints;
- document units, time scales, coordinate frames and array shapes;
- avoid premature classes and abstract base classes;
- avoid broad catch-all exceptions;
- treat no-access as a valid result, not an error;
- never ignore SGP4 error codes;
- do not silently coerce invalid configuration;
- keep calculations deterministic unless a task explicitly introduces randomness;
- keep raw analysis products separate from summary metrics;
- avoid hidden global state; and
- avoid embedding plots or file writing inside propagation and geometry calculations.

Review-sensitive areas requiring explicit human attention:

- Walker phasing formula;
- SGP4 mean-element assumptions;
- gravity-constant selection;
- UTC and Skyfield time conversions;
- TEME and observer-coordinate handling;
- elevation and event semantics;
- access start/end boundary conventions;
- array dimensions and broadcasting;
- station-union access metrics;
- independent reference values; and
- performance claims.

---

# 13. Definition of done for an individual task

A development task is complete only when:

- requested behaviour is implemented;
- scope exclusions were respected;
- tests cover nominal, invalid and relevant boundary behaviour;
- relevant tests pass;
- units, frames, times and array shapes are explicit;
- assumptions are documented where needed;
- errors and valid empty results are handled appropriately;
- no unrelated refactor is included;
- the diff is reviewable; and
- the implementation remains consistent with the V0 architecture and future downstream interfaces.

---

# 14. Near-term implementation order

Use this order unless the human task lead explicitly changes it:

1. Create the minimal package and test structure.
2. Add the Stage 1 smoke YAML scenario.
3. Implement the minimum configuration schema.
4. Add configuration validation tests.
5. Construct one SGP4 satellite from documented inputs.
6. Propagate one satellite over the smoke time grid.
7. Check and expose SGP4 error status.
8. Calculate access to one ground station.
9. Define the first access-window result record.
10. Export one access-window file and minimal manifest.
11. Extend configuration to Walker 6/2/1 and two stations.
12. Implement/test Walker generation.
13. Extend propagation to `SatrecArray`.
14. Calculate all Stage 2 satellite-station access windows.
15. Add metrics, exports and diagnostic plots.
16. Complete POC-01 acceptance and reference checks.
17. Add the Stage 3 scale scenario.
18. Profile and record performance before optimising.

---

# 15. Summary for Antigravity

The immediate goal is not to build the complete LEO-PNT dissemination simulator. The immediate goal is to create a small, generic and reusable V0 mission-analysis foundation.

The first implementation target is a one-satellite/one-station smoke flow. The main POC is a six-satellite Walker 6/2/1 constellation propagated with accelerated SGP4 for 24 hours, with Skyfield-based access analysis to two generic ground stations. The same pipeline will later be scaled to 120 satellites and five stations to establish performance.

V0 should finish at library-independent ephemeris and geometric access products, basic access metrics, exports and provenance. Contact planning, routing, traffic and dissemination are downstream V1/V2 functions.

Keep implementation narrow, transparent and testable. Use the selected libraries rather than recreating domain functionality. Preserve important modular boundaries, but do not over-engineer abstractions for capabilities that are not yet required.
