# Cross-Cutting Contract: Application Filesystem Layout — v0.9 DRAFT

## Base directory resolution (order is normative)
1. `$WIN10DRB_HOME` if set, absolute, and writable.
2. Otherwise `$XDG_STATE_HOME/win10drb`
   (defaults to `~/.local/state/win10drb`).

The resolved base shall be created with mode 0700. All files below it 0600.
Reports and databases contain sensitive metadata (SRS §3.6); no world-readable
artifacts.

## Layout
<base>/
  sessions/<session_id>/           0700   one directory per session (UUID name)
    win10drb.sqlite                0600   active session database
    manifests/<source_id>.txt      0600   app-generated manifests (default location)
  mounts/<source_id>/              0700   application-owned ntfs-3g mount points
  logs/win10drb.log                0600   local diagnostic log; never leaves the machine

## Rules
1. Nothing shall be written to a scanned source or anywhere inside a mount point.
2. `db.py` receives the database path from the coordinator; it never resolves paths.
3. Manifest generation writes to `sessions/<id>/manifests/` by default; the user
   may choose another writable location via the export dialog (SRS FR-1.6), and
   user-chosen paths override the default.
4. Report export defaults to suggesting `sessions/<id>/report.json` in the file
   dialog; the user chooses the final location.
5. `report import` creates a fresh session directory and database; the previous
   session's directory is left intact.
6. Mount points are created by the mount manager under `mounts/` as the normal
   user (no elevation needed for mkdir when base is user-owned); they are removed
   after successful unmount.
7. Startup orphan sweep ([src/README](../../src/README.md) §5.1): at launch, the
   mount manager inspects `<base>/mounts/*`, cross-references `/proc/mounts`, and
   offers guided release for any still-mounted application-owned directories.
8. Live Session caveat: on a Live USB, `<base>` under `$HOME` is RAM-backed and
   does not survive reboot. The status bar tooltip shall remind the user that
   reports must be exported to persistent media. `$WIN10DRB_HOME` exists so a
   user can relocate everything to a writable USB stick.