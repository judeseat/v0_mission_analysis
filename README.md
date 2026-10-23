# v0_mission_analysis

General-purpose satellite mission-analysis and ground-access modelling foundation (V0).

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
