# v0_mission_analysis

General-purpose satellite mission-analysis and ground-access modelling foundation (V0).

> **Scope Note:** V0 currently models analytical SGP4 orbit propagation and line-of-sight geometric ground access above an elevation threshold. It does not model communications links, radio-frequency budgets, antenna contention, contact scheduling, network routing, or data dissemination.

---

## Environment Setup (Windows)

Prerequisites: Python 3.12 installed on your system path or accessible via the Windows Python Launcher (`py`).

### 1. Create Virtual Environment

```powershell
py -3.12 -m venv .venv
```

### 2. Activate Virtual Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

*(If script execution is restricted in PowerShell, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activation).*

### 3. Install Package in Editable Mode

Install `v0_tool` with development dependencies:

```powershell
pip install -e .[dev]
```

### 4. Run Test Suite

```powershell
pytest
```

---

## Executing the Stage 1 Smoke Workflow

Run the Stage 1 single-satellite smoke workflow from the repository root:

```powershell
python -m v0_tool scenarios/smoke_01.yaml
```

### Expected Output

Upon successful execution, the command outputs a concise summary to `stdout`:
```text
Smoke workflow completed successfully.
Scenario ID:         smoke_01
Run ID:              smoke_01_<uuid>
Ephemeris samples:   73
Access windows:      1
Execution duration:  0.0105 s
Output directory:    C:\...\outputs\smoke_01\smoke_01_<uuid>
```

### Generated Files

The run creates a dedicated, un-overwritten directory beneath the configured output path:
```text
outputs/smoke_01/<run_id>/
├── validated_scenario.json   # Serialized validated scenario configuration
├── ephemeris.csv             # Time-series states in TEME frame (position in km, velocity in km/s)
├── access_windows.csv        # Discrete geometric ground-access windows
└── run_manifest.json         # Execution metadata, software versions, Git status, and assumptions
```
