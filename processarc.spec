# PyInstaller spec for ProcessArc.exe (the Windows desktop build).
#
# Run via the workflow `.github/workflows/build-windows.yml`, which on a
# Windows runner does (paraphrased):
#
#     npm --prefix frontend ci
#     npm --prefix frontend run build           # produces frontend/dist
#     pip install -r backend/requirements.txt pyinstaller
#     pyinstaller processarc.spec
#
# The resulting single-file binary lands at `dist/ProcessArc.exe`.
#
# Building manually on Windows (the same commands above) is also
# supported — see docs/windows_build.md.
#
# Notes:
#   - Single-file mode (onefile=True) — slower first launch (~2s of
#     temp extraction) but ships as one .exe the user can drag anywhere.
#   - console=False — no console window in production. Crashes go to
#     <user-data-dir>/logs/app.log instead (see backend/desktop.py).
#   - We deliberately bundle the entire backend package + frontend/dist
#     and let PyInstaller's analysis pick up imports. Hidden imports
#     below cover the few things its static analyzer misses (mostly
#     uvicorn protocol implementations that get selected at runtime).

# ruff: noqa
# pyright: reportMissingImports=false
# This file is executed by PyInstaller, not imported normally — the
# `Analysis`, `PYZ`, `EXE` names are injected into the namespace at
# build time by the pyinstaller runtime.

from pathlib import Path

# `__file__` is not defined when PyInstaller execs this spec, but the
# current working directory is the directory containing the spec
# (the repo root in our case), so a plain relative path is fine.
REPO_ROOT = Path('.').resolve()


a = Analysis(
    ['backend/desktop.py'],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    # Bundle the built React app at <bundle>/frontend/dist — matches
    # the lookup in backend/api/main.py:_frontend_dist_dir().
    datas=[
        ('frontend/dist', 'frontend/dist'),
    ],
    hiddenimports=[
        # uvicorn picks its HTTP / lifespan / websockets implementations
        # by string at runtime; static analysis misses them.
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # backend routers are discovered via include_router calls but
        # listed explicitly here so a missing one fails the build
        # rather than the runtime.
        'backend.api.routers.export',
        'backend.api.routers.extract',
        'backend.api.routers.projects',
        'backend.api.routers.settings',
        'backend.features.ignition_tags.router',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # We don't need tests in the bundle.
        'pytest',
        'backend.tests',
        # uvloop is not available on Windows; uvicorn falls back
        # cleanly to asyncio without it.
        'uvloop',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ProcessArc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX trips antivirus on many Windows installs
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # No console window — see backend/desktop.py for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='frontend/src/assets/processarc-logo-light.png',  # Add a .ico
    # later if you want a custom taskbar icon; PyInstaller wants .ico
    # specifically on Windows.
)
