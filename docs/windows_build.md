# Building ProcessArc.exe (Windows desktop)

ProcessArc ships as a single-file Windows executable that bundles the
Python backend, the built React frontend, and the Python runtime. The
end user double-clicks `ProcessArc.exe`, their default browser opens to
the app, and there's nothing to install.

## Triggering a build

The build runs on GitHub Actions on a Windows runner — you don't need a
Windows machine.

### Option 1 — Manual build (most common)

1. Go to **Actions** → **Build Windows .exe** in the GitHub repo
   (`https://github.com/rlesovsky/ProcessArc/actions/workflows/build-windows.yml`).
2. Click **Run workflow** → **Run workflow** (default branch is fine).
3. Wait ~5 minutes. When the run finishes green, scroll to the bottom
   of the run summary — the artifact **`ProcessArc-windows-exe`**
   contains `ProcessArc.exe` (~30–60 MB). Download, unzip, run.

Artifacts expire after 90 days.

### Option 2 — Release build (for distribution)

Tag a commit on `main` and push the tag — the workflow runs
automatically and attaches the .exe to a GitHub Release.

```bash
git tag v0.1.0
git push origin v0.1.0
```

The Release lives at
`https://github.com/rlesovsky/ProcessArc/releases/tag/v0.1.0` and the
binary is a public download (good for sharing a link with someone who
doesn't have GitHub access to the repo).

## What ends up in the .exe

| Component | Source | Size in bundle |
|---|---|---|
| Python 3.11 runtime | GitHub runner | ~15 MB |
| Backend (`backend/`) | This repo | ~2 MB |
| FastAPI + uvicorn + pydantic + anthropic SDK + openpyxl + python-docx | `backend/requirements.txt` | ~25 MB |
| Built React app (`frontend/dist/`) | `npm run build` | ~1 MB |

PyInstaller compresses + de-duplicates, so the final binary is usually
30–60 MB depending on dep versions.

## Where the .exe stores data

The bundled build keeps no state inside the exe (which lives in a temp
extraction folder and gets wiped each launch). All user data goes to a
per-user app data directory:

- **Windows:** `%APPDATA%\ProcessArc\`
- **macOS** (if you ever build for mac): `~/Library/Application Support/ProcessArc/`
- **Linux:** `~/.config/processarc/`

Inside that directory:

| Path | Purpose |
|---|---|
| `.env` | Anthropic API key + model selection (set through the UI) |
| `projects/` | Per-project working state and generated deliverables |
| `templates/` | Customer / vendor template workbooks read at runtime |
| `logs/app.log` | Rotating launcher log (1 MB × 3 files) — start here when debugging crashes |

## When something goes wrong

The .exe launches with no visible console, so all errors land in
`%APPDATA%\ProcessArc\logs\app.log`. Open it in Notepad or any text
editor to see the traceback.

The CI workflow includes a smoke test that boots the freshly-built .exe
and hits `/health` before publishing the artifact, so a fundamentally
broken binary fails the build instead of getting released.

## Building locally on Windows (alternative)

If you have a Windows machine and want a faster iteration loop than CI:

```powershell
# In the repo root, with Node 20 and Python 3.11 on PATH:
cd frontend
npm ci
npm run build
cd ..

python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install pyinstaller==6.10.0

pyinstaller --clean --noconfirm processarc.spec
# Output lands at dist\ProcessArc.exe
```

The local build uses the same `processarc.spec` and produces a binary
indistinguishable from the CI build.

## Cross-compilation note

PyInstaller is platform-native — you can't build a Windows .exe on
macOS or Linux. GitHub Actions' Windows runner is the path of least
resistance. If you ever need to build without GitHub, a Windows VM
(Parallels, UTM, etc.) running the steps above is the next-simplest
option.
