# Third-Party Notices and Licence Review Register

This document tracks third-party dependencies used in the V0 generic mission-analysis foundation.
In accordance with project guardrails, all upstream licence details recorded below are provisional, sourced directly from package metadata, and subject to human engineering and legal review prior to operational or contractual adoption. No definitive legal conclusion is asserted here.

## 1. Runtime Dependencies

| Package (PyPI) | Intended Role | Upstream-Reported Licence (Provisional) | Review Status |
| :--- | :--- | :--- | :--- |
| `numpy` | Coordinate/velocity arrays, time grids, vectorized calculations | BSD 3-Clause | Pending human engineering review |
| `sgp4` | Analytical SGP4 satellite orbit propagation | MIT | Pending human engineering review |
| `skyfield` | Astrometry, topocentric frames, time conversions | MIT | Pending human engineering review |
| `pydantic` | Scenario schema definition and validation | MIT | Pending human engineering review |
| `pyyaml` | YAML scenario ingestion | MIT | Pending human engineering review |
| `matplotlib` | Diagnostic static plots | PSF-based / Matplotlib License | Pending human engineering review |

## 2. Development Dependencies

| Package (PyPI) | Intended Role | Upstream-Reported Licence (Provisional) | Review Status |
| :--- | :--- | :--- | :--- |
| `pytest` | Test framework for unit, integration, and regression suites | MIT | Pending human engineering review |
| `hatchling` | Build backend for PEP 517/621 packaging | MIT | Pending human engineering review |

---
*Note: Full license texts, notices, and transitive dependency trees will be recorded once dependency resolution is locked.*
