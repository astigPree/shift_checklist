# Reviewed PyInstaller warnings

The Windows `onedir` build must pass `audit_pyinstaller_warnings.ps1`. The audit
uses an explicit allowlist so a newly missing import stops the build until it is
investigated.

The diagnostic build currently reports 48 known conditional imports and zero
unexpected missing modules. They are not application dependencies:

- Unix-only standard-library branches such as `posix`, `pwd`, `grp`, `fcntl`,
  `termios`, and `resource`.
- Android, iOS, JVM, and legacy-Python branches such as `android`, `jnius`,
  `ios`, `java`, `Queue`, and `ConfigParser`.
- Optional providers and integrations that Shift Checklist does not use, such
  as camera/game/input modules, NumPy/Pillow acceleration, Trio, SMB, and CTags.
- Dynamic-import false positives from PyInstaller, multiprocessing, Pygments,
  and Kivy provider discovery.

Required Windows runtime providers, Plyer notification support, application
modules, KV layout, icon files, sound directory, and handoff documents are
validated after every diagnostic and release build by `package_smoke.ps1`.
