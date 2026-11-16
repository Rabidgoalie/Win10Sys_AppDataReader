# Module Contract: mount_manager — v1.0.0 DRAFT

Tier: 1 (rolling freeze) · Sheet: `docs/contracts/mount_manager.md` ⇄ `src/mount_manager.py`
Issued: 2026-11-16 · Author: Forensic Systems Architect (drafting pass) · Status owner: Project Coordinator
Generated against: `models` v1.1.0 FROZEN (Tier 0), DDD schema v1.0.0, SRS/SDD/ADR as attached.
Direct dependencies (per `src/README.md` §1.2): `models` only. **No `pathnorm`, no `db`, no `config/*`, no `queue`.**
Direct dependents: `coordinator`, `main`.
Freeze gate: reviewer sign-off on §9.1 deviations + §9.3 verification items, then coordinator promotion.
Machine-checked surface: the single `python` fence in §1 (`test_contract_sheet[mount_manager.md]`).

## 1. Public API

```python
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from models import (
    AcquisitionMethod,
    BlockDevice,
    PreparedSource,
    SourceRecord,
    SourceRole,
    SourceType,
)

# ── Public constants (normative safety surface) ─────────────────────────
SAFE_MOUNT_OPTIONS: tuple[str, ...] = (
    "ro",
    "norecover",
    "noatime",
    "nodev",
    "nosuid",
    "noexec",
    "streams_interface=none",
)

FORBIDDEN_MOUNT_OPTIONS: frozenset[str] = frozenset({
    "rw", "force", "recover", "remove_hiberfile", "acl", "permissions",
    "inherit", "user_xattr", "show_sys_files", "hide_hid_files",
    "hide_dot_files", "efs_raw", "sync", "dirsync", "atime", "relatime",
    "uid=0", "gid=0", "umask=000", "umask=022", "dmask=000", "fmask=000",
})

LSBLK_COLUMNS: tuple[str, ...] = (
    "NAME", "PATH", "TYPE", "FSTYPE", "SIZE", "LABEL", "UUID",
    "MOUNTPOINT", "MOUNTPOINTS", "TRAN", "PARTLABEL",
)

LSBLK_FALLBACK_COLUMNS: tuple[str, ...] = (
    "NAME", "PATH", "TYPE", "FSTYPE", "SIZE", "LABEL", "UUID",
    "MOUNTPOINT", "TRAN", "PARTLABEL",
)

NTFS_MOUNT_FSTYPES: frozenset[str] = frozenset({
    "ntfs", "ntfs3", "fuseblk", "fuse.ntfs-3g",
})

PROTECTED_MOUNT_POINTS: frozenset[str] = frozenset({
    "/", "/boot", "/boot/efi", "/cdrom", "/dev", "/home", "/proc",
    "/run", "/sys", "/tmp", "/usr", "/var",
})

# ── Callback seam (SDD §2.7) ────────────────────────────────────────────
# (explanation_message, existing_mount_points) -> user_approved
UnmountConfirmCallback = Callable[[str, tuple[str, ...]], bool]

# ── Enumerations ────────────────────────────────────────────────────────
class ReleaseStatus(StrEnum):
    RELEASED = "released"
    NOT_TRACKED = "not_tracked"
    DECLINED = "declined"
    BUSY = "busy"
    FAILED = "failed"

class ElevationState(StrEnum):
    READY = "ready"
    NEEDS_TERMINAL = "needs_terminal"
    UNAVAILABLE = "unavailable"

# ── Result value objects ────────────────────────────────────────────────
@dataclass(frozen=True)
class ReleaseOutcome:
    source_id: str
    status: ReleaseStatus
    mount_point: Path | None = None
    lazy: bool = False
    still_mounted: bool = False
    detail: str | None = None

@dataclass(frozen=True)
class ElevationProbe:
    state: ElevationState
    sudo_path: str | None = None
    detail: str | None = None
    cancelled: bool = False

# ── Exception taxonomy ──────────────────────────────────────────────────
class MountError(Exception):
    """Base class; also raised directly for host-environment failures."""

class DeviceEnumerationError(MountError):
    """lsblk unavailable, failed, timed out, or produced unparseable JSON."""

class ElevationError(MountError):
    """sudo unusable, declined, expired, or not permitted for this user."""

class SourcePreparationError(MountError):
    """Recoverable, per-source preparation failure (incl. user decline)."""

class UnsafeMountError(MountError):
    """A mount was obtained but failed read-only safety verification."""

class PreparationCancelled(MountError):
    """Cancellation observed; all rollback completed before this was raised."""

class CriticalIoError(MountError):
    """Suspected failing media. Stops all source access (SRS §3.9, ADR-12)."""
    device_path: str | None
    operation: str
    def __init__(self, message: str, *, device_path: str | None = None,
                 operation: str = "") -> None: ...

# ── Pure helper (stateless, ADR-16) ─────────────────────────────────────
def build_safe_mount_options(uid: int, gid: int) -> str: ...

# ── Stateful acquisition authority (ADR-16) ─────────────────────────────
class MountManager:
    def __init__(self, base_mount_dir: Path, *,
                 command_timeout_seconds: float = 60.0,
                 discovery_timeout_seconds: float = 15.0,
                 elevation_timeout_seconds: float = 120.0) -> None: ...
    def __enter__(self) -> MountManager: ...
    def __exit__(self, *exc) -> None: ...

    @property
    def base_mount_dir(self) -> Path: ...

    # --- Discovery (SRS FR-1.2; never on the Tk thread) ---
    def list_block_devices(self) -> list[BlockDevice]: ...

    # --- Elevation (ADR-14; never on the Tk thread) ---
    def probe_elevation(self) -> ElevationProbe: ...
    def prime_elevation(self, *,
                        cancel_event: threading.Event | None = None) -> ElevationProbe: ...

    # --- Preparation (SRS §3.8, FR-1.11, ADR-5) ---
    def prepare_source(
        self,
        source: SourceRecord,
        *,
        confirm_unmount: UnmountConfirmCallback | None = None,
        confirm_lazy: UnmountConfirmCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> PreparedSource: ...

    # --- Release (SRS §3.8, ADR-5; deliberately not cancellable) ---
    def release_source(self, source_id: str, *,
                       confirm_lazy: UnmountConfirmCallback | None = None) -> ReleaseOutcome: ...
    def release_all(self, *,
                    confirm_lazy: UnmountConfirmCallback | None = None) -> tuple[ReleaseOutcome, ...]: ...
    def release_orphan(self, mount_point: Path, *,
                       confirm_lazy: UnmountConfirmCallback | None = None) -> ReleaseOutcome: ...

    # --- Startup hygiene (ADR-18, README §5.1) ---
    def sweep_orphans(self) -> list[Path]: ...

    # --- Non-blocking state accessors (Tk-thread safe) ---
    def tracked_source_ids(self) -> tuple[str, ...]: ...
    def mount_point_for(self, source_id: str) -> Path | None: ...
    def unreleased_mounts(self) -> tuple[ReleaseOutcome, ...]: ...
```

## 2. Postconditions

### 2.1 `build_safe_mount_options(uid, gid)`

1. Returns exactly `",".join(SAFE_MOUNT_OPTIONS + (f"uid={uid}", f"gid={gid}", "umask=077"))`. Token order is contract; the acceptance vector is:
   `build_safe_mount_options(1000, 1000) == "ro,norecover,noatime,nodev,nosuid,noexec,streams_interface=none,uid=1000,gid=1000,umask=077"`.
2. Total and pure for `uid >= 0 and gid >= 0`; raises `ValueError` for negative values or non-`int` inputs. Performs no I/O.
3. The result never contains any member of `FORBIDDEN_MOUNT_OPTIONS`, for any `uid`/`gid` including `0`. `set(SAFE_MOUNT_OPTIONS) & FORBIDDEN_MOUNT_OPTIONS == frozenset()`.
4. `umask=077` is unconditional. Combined with `uid`/`gid` of the *invoking desktop user*, this satisfies SRS §3.8 "present mounted files only to the invoking desktop user".
5. Rationale for each token (normative intent, verified per §9.3):
   - `ro` — kernel-enforced read-only; the only write barrier that does not depend on application discipline.
   - `norecover` — never replay `$LogFile`. Dirty volumes mount read-only; the dirty bit is never cleared.
   - `noatime` — no access-time metadata intent, defence in depth behind `ro`.
   - `nodev`, `nosuid`, `noexec` — the mounted volume cannot host device nodes, setuid binaries, or executable mappings; supports SRS §3.1 "shall not execute Windows binaries".
   - `streams_interface=none` — alternate data streams are not exposed; consistent with `pathnorm` ADS stripping.
6. `remove_hiberfile`, `recover`, `force`, `rw`, `show_sys_files`, `hide_hid_files`, `hide_dot_files` shall never be emitted on any code path, including failure/retry paths. `hide_hid_files`/`hide_dot_files` are specifically prohibited because `NTUSER.DAT` and `UsrClass.dat` carry the hidden attribute; hiding them would silently defeat offline hive discovery.
7. The shorthand "`ro,ro_dirty`" used in earlier review notes is **not** an option vector: `ro_dirty` is not a recognised `ntfs-3g` option and would abort every mount. Its intent (read-only tolerance of a dirty volume, without repair) is realised by `ro,norecover`. See §9.1 DEV-4.

### 2.2 `MountManager.__init__` / `base_mount_dir`

1. `base_mount_dir` is expanded (`expanduser()`) and resolved to an absolute path; the property returns that resolved path for the lifetime of the instance.
2. `ValueError` (caller-contract violation) when the argument is empty, relative after expansion, `/`, or resolves under `/dev`, `/proc`, or `/sys`.
3. `MountError` (host-environment refusal) when the resolved base:
   - is under `/media`, `/mnt`, or `/run/media` (external-mount roots, SRS FR-1.10);
   - lies inside any mount-table entry whose filesystem type is in `NTFS_MOUNT_FSTYPES` (would write onto a Windows source);
   - exists but is not a directory, or is not owned by `os.getuid()`;
   - cannot be created.
4. Missing base directories are created with mode `0700` (parents likewise), per ADR-18. An existing base whose mode is looser than `0700` is **tightened** to `0700`; permissions are never loosened.
5. Construction performs no subprocess execution, no elevation, and no access to any scanned device. It reads the host mount table only.
6. `__enter__` returns `self`; `__exit__` calls `release_all()` with no callback and never suppresses exceptions.

### 2.3 `list_block_devices()`

1. Executes exactly one host command (§5.2 D-1) with the explicitly requested column list `LSBLK_COLUMNS`; `$PATH` is never consulted for binary resolution.
2. Parses `lsblk --json` defensively: the top-level object must contain a `blockdevices` list; each node must be a mapping. Anything else raises `DeviceEnumerationError`.
3. Field mapping onto `models.BlockDevice`:
   - `device_path` ← `PATH` (falls back to `NAME`, which is a full path under `--paths`); must start with `/dev/`, else the node is skipped.
   - `name` ← `os.path.basename(device_path)`.
   - `dev_type` ← `TYPE` (lowercased, stripped).
   - `fs_type` ← `FSTYPE` (lowercased, stripped; empty → `None`).
   - `size_bytes` ← `SIZE` parsed as a base-10 integer (`--bytes` guarantees integers); non-numeric, negative, or null → `None`.
   - `label`, `uuid`, `transport` (`TRAN`), `part_label` (`PARTLABEL`) ← stripped strings; empty → `None`.
   - `mount_points` ← union of `MOUNTPOINTS` (list or scalar or null) and `MOUNTPOINT` (scalar or null), each unescaped (§2.3.6), empties dropped, deduplicated, **sorted lexicographically**.
   - `child_count` ← number of **direct children in the raw JSON node, before any filtering**, of any type.
4. Candidate selection (SRS FR-1.2). A node is returned only if all hold:
   - `dev_type ∈ {"disk", "part"}`; every other type (`loop`, `rom`, `lvm`, `crypt`, `raid*`, `mpath`, …) is excluded;
   - `device_path` basename does not begin with `loop`, `ram`, `zram`, `sr`, `fd`, `dm-`, `md`, `nbd`;
   - `fs_type == "ntfs"` (this alone excludes `swap`, `squashfs`, `iso9660`, `crypto_LUKS`, `LVM2_member`, `BitLocker`, `exfat`, `vfat`, `ext*`);
   - if `dev_type == "disk"`: `child_count == 0` (whole-disk NTFS only when unpartitioned);
   - `device_path` is not already returned (deduplicated by resolved path).
   Children are visited recursively; a partition nested under an excluded parent is still evaluated on its own merits.
5. Result ordering is deterministic: natural (numeric-aware) sort by `device_path`, so `/dev/sda2` precedes `/dev/sda10`; ties broken by `name`.
6. Escaping: `\xNN` hex escapes (emitted by some `util-linux` builds even in JSON mode) and octal `\NNN` escapes are decoded before use; a mount point containing a space must survive round-trip.
7. `models.BlockDevice.is_ntfs_candidate` is a convenience predicate and is **not** the selection authority; §2.3.4 is. This module does not depend on the semantics of that property body (Tier 2 in `models`).
8. Discovery is a **host-side udev/sysfs query**. The module shall not invoke `blkid`, `file -s`, `dd`, `mount -t auto`, `udisksctl`, or any other sector-probing tool to "help" a device that has no `FSTYPE`. A device with absent udev metadata is simply not offered as a candidate. This prevents discovery itself from stressing a failing drive.
9. Failure of any kind (missing binary, non-zero exit, timeout, malformed JSON) raises `DeviceEnumerationError` with an actionable message. It is never classified as `CriticalIoError`.
10. Column-capability fallback: if the first invocation fails **and** stderr matches `unknown column` / `invalid column` / `unknown option` (case-insensitive), exactly one further invocation is made with `LSBLK_FALLBACK_COLUMNS`. This is a host-side capability probe, **not** a source-read retry, and is therefore compatible with ADR-12. Any second failure raises `DeviceEnumerationError`.
11. Requires no elevation and returns `[]` (not an error) when the host genuinely reports no NTFS candidates.

### 2.4 `probe_elevation()`

1. Executes `<abs sudo> -n true` with all standard streams detached (§5.2 E-1), bounded by a fixed 10-second timeout. Never prompts, never blocks on a terminal.
2. Returns:
   - `ElevationState.READY` — exit status 0 (passwordless sudo or a warm credential cache); `sudo_path` is the resolved absolute path.
   - `ElevationState.NEEDS_TERMINAL` — sudo exists and is executable but the probe failed; `detail` explains that the user must answer the prompt in the launching terminal (ADR-14).
   - `ElevationState.UNAVAILABLE` — sudo is absent, not a root-owned executable, the probe timed out, or `os.geteuid() == 0` (the application must not run as root; SRS §3.7 / ADR-11).
3. Never raises for environmental conditions; `cancelled` is always `False`.
4. Idempotent and side-effect-free with respect to source drives. May be called repeatedly; the last result is cached for `prepare_source`'s fast-fail check (§2.6.9).

### 2.5 `prime_elevation(*, cancel_event=None)`

1. Executes `<abs sudo> -v` with **inherited** stdin/stdout/stderr so the password prompt appears in the terminal the application was launched from (ADR-14). No `-S`, no `pkexec`, no in-app password dialog, ever.
2. Bounded by `elevation_timeout_seconds`. While the child runs, `cancel_event` is polled at ≤ 100 ms intervals.
3. Returns:
   - `READY` on exit status 0;
   - `NEEDS_TERMINAL` on timeout (the user has not answered yet) with an explanatory `detail`;
   - `NEEDS_TERMINAL` with `cancelled=True` when `cancel_event` was set — the child's process group is terminated and no credentials were cached;
   - `UNAVAILABLE` when sudo is missing, the user is not permitted to use it, or `os.geteuid() == 0`.
4. Returns normally on cancellation (ADR-15); it does not raise `PreparationCancelled`.
5. Shall be called at most once per scan start by the coordinator, before any `prepare_source` that requires mounting. It is the only blocking-on-human call in this module.

### 2.6 `prepare_source(source, *, confirm_unmount=None, confirm_lazy=None, cancel_event=None)`

**Common preconditions (both branches)**

1. `ValueError` — caller-contract violations, raised before any I/O:
   - `source.logical_drive` is `None` or empty (SDD §2.19 propagation rule);
   - `source.source_id` is not a single safe path component (empty, `.`, `..`, or containing `/`, `\`, `\0`);
   - `source_type == mounted_block_device` and `origin_device_path` is `None`;
   - `source_type == manifest_file` and `manifest_path` is `None`.
2. `source.logical_drive` is propagated verbatim into `PreparedSource.logical_drive`. This module does not parse, reformat, or reassign it — logical-drive assignment belongs to the coordinator (SDD §2.19) and `pathnorm` is not a dependency.
3. `PreparedSource.read_only` is always `True`; `session_id`, `source_id`, `source_type`, `source_role`, `label`, `uuid`, `size_bytes` are carried through unchanged from `source`.
4. A successful call is idempotent per `source_id`: preparing an already-tracked source returns the existing `PreparedSource` without issuing any command.

**Manifest branch (`source_type == manifest_file`)**

5. No mount, no elevation, no subprocess, no device access.
6. `manifest_path` is expanded and resolved; it must exist, be a regular file, and be readable (`os.access(R_OK)`). A zero-byte manifest is valid (an empty volume yields an empty manifest).
7. The resolved manifest path shall not lie inside `base_mount_dir` or inside any mount point tracked by this instance — that would be reading evidence from a scanned source through an application mount. Violation → `SourcePreparationError`.
8. Returns `PreparedSource(mount_point=None, manifest_path=<resolved str>, acquisition_method=NTFSLS_MANIFEST, fs_type=source.fs_type or "ntfs", logical_drive=source.logical_drive, …)`. Nothing is tracked; `release_source` for this id is a no-op.

**Mounted branch (`source_type == mounted_block_device`)**

9. Fast-fail elevation gate: if the most recent probe is not `READY`, a fresh `probe_elevation()` is taken; if still not `READY`, raise `ElevationError` with terminal guidance. `prepare_source` never blocks on a password prompt and never invokes `sudo -v` itself.
10. Device validation: `origin_device_path` must be absolute, start with `/dev/`, and `os.stat` must report a block device (`stat.S_ISBLK`). The device identity used everywhere below is `os.major/os.minor` of `st_rdev`, not the path string — this defeats `/dev/disk/by-*` aliasing.
11. The device must not already be prepared under a different tracked `source_id` (same major:minor) → `SourcePreparationError`.
12. Current mount state is re-read from `/proc/self/mountinfo` at preparation time (never from the `lsblk` snapshot the user selected minutes earlier). An entry matches the device when **either** its `major:minor` field equals the device identity **or** its mount-source field resolves to the same block device. Both tests are required: `fuseblk` mounts carry an anonymous fuse device number, not the underlying block device number.
13. If matching entries exist:
    - every matching entry's filesystem type must be in `NTFS_MOUNT_FSTYPES`; a foreign type → `SourcePreparationError` (refuse to unmount something unexpected);
    - no matching mount point may be in `PROTECTED_MOUNT_POINTS`, nor be an ancestor of `base_mount_dir`, `sys.executable`, or `os.getcwd()` → `SourcePreparationError` (never unmount the running system or the Live medium);
    - `confirm_unmount` is invoked once with `(message, tuple(sorted(mount_points)))`. `None` callback or `False` → `SourcePreparationError` (declined); nothing is unmounted;
    - each mount point is unmounted with the normal vector (§5.2 U-1), in sorted order;
    - if a normal unmount reports busy and `confirm_lazy` is present, it is invoked with a lazy-specific message; `True` → lazy vector (§5.2 U-2); `None`/`False` → `SourcePreparationError`;
    - after the sequence, the mount table is re-read; any surviving matching entry → `SourcePreparationError`. The module never mounts over an existing mount.
14. Confirmation message content is contract; exact wording is Tier 2. The unmount message must state: the existing mount is unsupported, the listed mount points will be closed, the application will re-open the drive read-only, and no data will be written by the application. The lazy message must additionally state that programs may still be using the drive and that a deferred unmount detaches it immediately while closing it in the background. Both must be calm and non-blaming (UIDD §11).
15. Mount point creation: `<base_mount_dir>/<source_id>/`, created unprivileged with mode `0700`. It must be a real directory (not a symlink), must be empty, and must not already be a mount point. Creation is **not** elevated (§9.1 DEV-3).
16. Tracking is registered **before** the privileged mount command is issued, so a timed-out or partially successful mount is always discoverable by `release_all`.
17. The mount command is §5.2 M-1 with `-o build_safe_mount_options(os.geteuid(), os.getegid())`. Exactly one attempt; no retry of any kind.
18. Post-mount verification, all mandatory:
    - a mount-table entry exists for the mount point;
    - its per-mount options contain `ro`;
    - `os.statvfs(mount_point).f_flag & os.ST_RDONLY` is set.
    Any failure → immediate normal unmount attempt, then `UnsafeMountError`. If the unmount cannot complete, the mount is recorded in `unreleased_mounts()` and `UnsafeMountError` is still raised. **A writable mount is never returned to the caller.**
19. Returns `PreparedSource(mount_point=str(mount_point), origin_device_path=source.origin_device_path, acquisition_method=NTFS3G_RO, fs_type="ntfs", read_only=True, logical_drive=source.logical_drive, …)`.
20. The module does not inspect volume contents to decide whether the volume "looks like Windows". Hive discovery is `hive_locator`'s responsibility; reading a possibly dying drive to satisfy curiosity is prohibited.

**Cancellation and rollback**

21. `cancel_event` is checked at these boundaries: entry; after mount-table inspection; after each confirmation callback returns; after each unmount command; before mount-point creation; before the mount command; after verification.
22. On cancellation the instance rolls back everything it created in this call: any mount it obtained is unmounted (normal only), any directory it created is removed (`os.rmdir`, empty-only), and tracking is cleared. `PreparationCancelled` is raised **only after rollback completes**.
23. External unmounts already performed are **not** reversible and are not undone. This is logged, and the coordinator must surface it as a warning; the contract makes no promise to restore the user's original mount.
24. Cancellation never leaves a tracked mount, a leaked mount point directory, or a half-populated `PreparedSource`.

### 2.7 `release_source(source_id, *, confirm_lazy=None)`

1. Never raises for environmental or device conditions; all outcomes are expressed as `ReleaseOutcome`. (`ValueError` is reserved for a non-string/empty `source_id`.)
2. Unknown or already-released id → `ReleaseOutcome(source_id, NOT_TRACKED)`; idempotent, no commands issued.
3. Normal unmount first (§5.2 U-1). Success → `RELEASED`, `still_mounted=False`, `lazy=False`; the mount point directory is then removed with `os.rmdir` after re-verifying it is not a mount point.
4. Busy **with** `confirm_lazy`: callback invoked; `True` → lazy unmount (§5.2 U-2) → `RELEASED` with `lazy=True`; `False` → `DECLINED`, `still_mounted=True`, retained in `unreleased_mounts()`.
5. Busy **without** `confirm_lazy` (e.g. exit path, UI gone) → `BUSY`, `still_mounted=True`, retained for the startup sweep. **Lazy unmount is never performed silently.**
6. Any other failure, including timeout → `FAILED`, `still_mounted` set from a fresh mount-table read, `detail` carries the actionable reason. Release timeouts are never escalated to `CriticalIoError` (§3.4).
7. `source_id` is removed from active tracking on `RELEASED` only.

### 2.8 `release_all(*, confirm_lazy=None)`

1. Iterates a snapshot of tracked ids in **source-preparation order** and calls `release_source` for each; returns one `ReleaseOutcome` per tracked source, in that order.
2. Best-effort: a failure of one source never aborts the remaining releases.
3. Safe to call multiple times; the second call returns outcomes only for whatever remains unreleased (empty tuple when everything is released).
4. Accepts no `cancel_event` by design: cleanup must complete during cancellation, failure, and exit (SRS §3.8).
5. Does not close or flush anything belonging to `db`, `state`, or the UI; it owns mounts only.

### 2.9 `release_orphan(mount_point, *, confirm_lazy=None)`

1. Intended for mounts discovered by `sweep_orphans()` after a crash, i.e. not present in this instance's tracking.
2. The resolved path must be a direct child of `base_mount_dir` **and** present in the mount table; otherwise `ReleaseOutcome(mount_point.name, NOT_TRACKED, detail=…)` with no commands issued.
3. Otherwise identical semantics to §2.7, with `source_id = mount_point.name` (the ADR-18 layout guarantees the directory name is the source id).
4. Never touches a path outside `base_mount_dir`, never follows a symlinked leaf, and never removes a directory that is still a mount point.

### 2.10 `sweep_orphans()`

1. Read-only detection. **Performs no unmount, no removal, no elevation, and no device access.**
2. Returns the sorted `list[Path]` of direct children of `base_mount_dir` that (a) are currently mount points according to `/proc/self/mountinfo`, (b) are directories owned by `os.getuid()`, (c) have mode bits `& 0o077 == 0`, and (d) are not tracked by this instance.
3. Returns `[]` when the base does not exist or the mount table is unreadable; unreadability is logged, not raised (startup hygiene must not prevent the application from launching).
4. Empty leftover directories are **not** removed by the sweep; they are reused or rejected by the next `prepare_source`. This keeps the sweep strictly non-destructive and race-free against a concurrent preparation.

### 2.11 State accessors

1. `tracked_source_ids()` → tuple of currently mounted source ids in preparation order.
2. `mount_point_for(source_id)` → the absolute `Path` while mounted, else `None`.
3. `unreleased_mounts()` → tuple of retained `ReleaseOutcome` records with `still_mounted=True`, in first-failure order. An entry is dropped only when a later release of that mount succeeds.
4. All three are non-blocking (state lock only, no I/O, no subprocess) and are the **only** methods permitted on the Tk thread. They return immutable snapshots; mutating the returned objects is impossible.

### 2.12 Cross-cutting invariants

1. Every host path returned by this module is absolute and resolved. DTO fields keep the types declared in `models` (`PreparedSource.mount_point` is `str`); module-local APIs use `pathlib.Path`.
2. No method ever returns a mount point that has not passed §2.6.18 verification.
3. No method ever writes to, or creates a path beneath, a mounted source.
4. The module never calls `shutil.rmtree`, `os.remove`, `os.unlink`, or `Path.unlink` anywhere. Directory removal is `os.rmdir` on verified-empty, verified-unmounted paths only.

## 3. Error contract

### 3.1 Taxonomy and caller mapping

| Condition | Surface | Coordinator disposition |
|---|---|---|
| Caller-contract violation (`logical_drive is None`, bad `source_id`, missing required path, relative base, negative uid/gid) | `ValueError` | Programmer error; not caught (ADR-19 philosophy) |
| `lsblk` missing / non-zero / timeout / malformed JSON | `DeviceEnumerationError` | `DeviceListEvent(devices=(), error=…)` |
| Base directory unusable, host binary missing, `/proc` unreadable at prepare time, running as root | `MountError` (base) | `ScanFailedEvent` with manual-install/permission guidance |
| sudo absent, declined, expired, not permitted | `ElevationError` | Terminal-guidance dialog + re-prime, else `ScanFailedEvent` |
| User declined unmount or lazy unmount | `SourcePreparationError` | Primary → `ScanFailedEvent`; secondary → `WarningEvent(acquisition)` + `SourceStatus.ERROR`, scan continues |
| Dirty/hibernated volume refused even read-only; wrong/invalid NTFS; busy mount point; unrecognised mount failure | `SourcePreparationError` | Primary → fatal; secondary → `WarningEvent` advising manifest generation (SRS §3.8) |
| Mount obtained but not verifiably read-only | `UnsafeMountError` | Fatal scan error + `WarningEvent(acquisition, critical)`. **Never** `CriticalIoFailureEvent` |
| `cancel_event` observed during preparation | `PreparationCancelled` | Cancellation transition (SDD §4.7); no failure dialog |
| Suspected media I/O failure (§3.2) | `CriticalIoError` | `CriticalIoFailureEvent(message, device_path)`, set cancel event, stop all source access, `release_all` |
| Unmount busy / declined / failed | `ReleaseOutcome` (no exception) | `WarningEvent(acquisition, warning)` naming the still-mounted path |
| Corrupt/absent registry hives, malformed manifests, SQLite errors | Out of scope for this module | — |

### 3.2 Critical-I/O classification (SRS §3.9, ADR-12, ADR-19 parity)

A failure is classified `CriticalIoError` **only** when it occurs inside a source-touching command (`ntfs-3g` mount) or a source read, **and** one of the following holds:

- an errno token in `{EIO(5), ENXIO(6), ENODEV(19), ETIMEDOUT(110), EREMOTEIO(121), ENOMEDIUM(123), EMEDIUMTYPE(124)}` is present in the raised `OSError` or the command stderr;
- stderr contains (case-insensitive) any of: `input/output error`, `i/o error`, `medium error`, `unrecoverable read error`, `read error`, `failed to read`, `no such device`, `medium not present`, `device not ready`;
- the `ntfs-3g` mount command exceeds `command_timeout_seconds` (a hung source command is treated as a failing-drive signal; the safe outcome is to stop).

`CriticalIoError` carries `device_path` (the origin device when known) and `operation` (`"mount"`, `"unmount"`, `"stat"`), suitable for direct construction of `CriticalIoFailureEvent`. No automatic retry is ever performed after classification.

### 3.3 Explicitly **not** critical

sudo/permission errors; `unknown option`; `target is busy`; missing host binaries; malformed `lsblk` JSON; host `/proc` read failure; `lsblk` timeouts; unmount timeouts; a declined confirmation. Misclassifying any of these as media failure would raise a false "your drive is dying" dialog and is a contract violation.

### 3.4 Release paths never escalate

`release_source`, `release_all`, `release_orphan` catch all `OSError` and `subprocess` failures internally and convert them to `ReleaseOutcome(FAILED, …)`. They never raise `CriticalIoError`: cleanup runs on exit and cancellation paths where no consumer can act on a critical event, and a busy FUSE daemon is not evidence of failing media.

### 3.5 Never swallowed

`ValueError` from caller-contract checks, and any exception raised *by a confirmation callback*, propagate to the caller after rollback (`try/finally`). A callback exception indicates a coordinator defect and shall not be disguised as a user decline (ADR-19).

### 3.6 Message content

Every raised message must be actionable and non-blaming (SRS FR-7.2, NFR-2): what happened, which device or path, and what the user can do next. Exact wording is Tier 2. Messages must never assert that data loss has occurred.

## 4. Events and warnings emitted

**This module emits no UI events and imports no event type or queue.** Event emission is the coordinator's responsibility (`models` §4, ADR-4, ADR-22 parity). The module surfaces typed results, typed exceptions, and callback invocations; the coordinator translates.

| Module surface | Coordinator translation (existing vocabulary; no Tier 0 amendment required) |
|---|---|
| `list_block_devices()` returns | `DeviceListEvent(devices=tuple(...), error=None)` |
| `DeviceEnumerationError` | `DeviceListEvent(devices=(), error=str(exc))` |
| `confirm_unmount` invocation | `ConfirmationRequestEvent(kind=UNMOUNT_EXTERNAL, message, details, request_id)`; worker blocks until `answer_confirmation` |
| `confirm_lazy` invocation | `ConfirmationRequestEvent(kind=LAZY_UNMOUNT, …)` |
| `ElevationProbe(NEEDS_TERMINAL)` | `WarningEvent(WarningRecord(category=ACQUISITION, severity=INFO/WARNING))` + terminal-guidance dialog, then `prime_elevation` |
| `prepare_source` returns | `SourcePreparedEvent(source=SourceRecord.from_prepared(...))` |
| `SourcePreparationError` (secondary) | `WarningEvent(category=ACQUISITION)` + `update_source_status(ERROR)` |
| `UnsafeMountError` | `WarningEvent(category=ACQUISITION, severity=CRITICAL)` + `ScanFailedEvent` |
| `CriticalIoError` | `CriticalIoFailureEvent(message, device_path)`; cancel event set; `release_all` |
| `ReleaseOutcome(still_mounted=True)` | `WarningEvent(category=ACQUISITION, severity=WARNING)` naming the mount point and the next-launch sweep |
| `sweep_orphans()` non-empty | Startup `WarningEvent(category=ACQUISITION)` + guided `release_orphan` flow |

Non-fatal observations internal to the module (column fallback used, base mode tightened, external unmount performed, cancellation rollback detail) are written to the module logger at `INFO`/`WARNING`. The logger is a private symbol (`_LOG`); log text is Tier 2.

## 5. I/O surface

### 5.1 Filesystem

| Path | Access | Notes |
|---|---|---|
| `/proc/self/mountinfo` | read | Authoritative mount table. Superset of `/proc/mounts` (ADR-18). Octal escapes `\040 \011 \012 \134` decoded in mount-point and root fields. |
| `/dev/<node>` | `os.stat` only | Metadata on the device node; **no `open()`, no read, no write, no ioctl**. |
| `<base>/mounts/` | create dir `0700`, tighten mode | Host-side only; never on a source. |
| `<base>/mounts/<source_id>/` | create dir `0700`; `os.rmdir` when empty and unmounted | Never `rmtree`, never recursive deletion. |
| `<base>/mounts/<source_id>/` (while mounted) | `os.statvfs` only | Read-only superblock query used for the `ST_RDONLY` assertion. No directory listing, no file open. |
| Manifest path (manifest branch) | `os.stat`, `os.access(R_OK)` | Existence/readability only. The manifest is never opened by this module. |
| Scanned source contents | **none** | No file is opened, listed, created, renamed, chmod-ed, or deleted on any source. |
| SQLite database | **none** | `db` is not a dependency (`src/README.md` §1.2). |
| Network | **none** | SRS §3.6. |

### 5.2 Privileged / host command allowlist (exact argv vectors)

All binaries are resolved from fixed absolute candidate lists, `realpath`-ed, and verified to be root-owned regular files with an executable bit. `$PATH` and `shutil.which` are never used. No shell is ever spawned (`shell=False`, no string commands). Every path argument is validated absolute and non-`-`-prefixed before inclusion.

| ID | Purpose | argv | stdio | Timeout |
|---|---|---|---|---|
| D-1 | Discovery | `[<lsblk>, "--json", "--bytes", "--paths", "--output", ",".join(LSBLK_COLUMNS)]` | in DEVNULL, out PIPE, err PIPE | `discovery_timeout_seconds` |
| D-1f | Column fallback (≤1) | same, with `LSBLK_FALLBACK_COLUMNS` | same | same |
| E-1 | Credential probe | `[<sudo>, "-n", "true"]` | all DEVNULL | 10 s fixed |
| E-2 | Credential prime | `[<sudo>, "-v"]` | **inherited** | `elevation_timeout_seconds` |
| U-1 | Normal unmount | `[<sudo>, "-n", "--", <umount>, <mount_point>]` | in DEVNULL, out/err PIPE | `command_timeout_seconds` |
| U-2 | Lazy unmount (confirmed only) | `[<sudo>, "-n", "--", <umount>, "-l", <mount_point>]` | same | same |
| M-1 | Safe read-only mount | `[<sudo>, "-n", "--", <ntfs-3g>, "-o", <option_string>, <device_path>, <mount_point>]` | same | same |

Binary candidates: sudo `/usr/bin/sudo`, `/bin/sudo`; lsblk `/usr/bin/lsblk`, `/bin/lsblk`; umount `/bin/umount`, `/usr/bin/umount`; ntfs-3g `/usr/bin/ntfs-3g`, `/bin/ntfs-3g`, `/usr/sbin/ntfs-3g`, `/sbin/ntfs-3g`.

`--` is passed to `sudo` only (its option parser is guaranteed to honour it); it is **not** passed to `ntfs-3g` or `umount`, whose parsers are not assumed to. Injection safety for the wrapped commands rests on the absolute-path/no-leading-dash precondition, which is enforced before execution.

### 5.3 Forbidden commands (hard invariant)

The module shall never invoke, in any path: `ntfsfix`, `fsck`, `fsck.ntfs`, `ntfsck`, `ntfsresize`, `ntfsclone`, `ntfsundelete`, `ntfscat`, `ntfsinfo` against a source, `chkdsk`, `mount`, `mount -t ntfs3`, `mount -t auto`, `udisksctl`, `systemd-mount`, `blkid`, `blockdev --setro/--setrw`, `hdparm`, `smartctl`, `dd`, `wipefs`, `sgdisk`, `parted`, `pkexec`, `su`, `sudo -S`, `sudo -i`, `sudo su`, or any shell (`sh`, `bash`, `zsh`). Drive-health tooling is out of scope (SRS §6).

### 5.4 Read-only guarantee chain

1. The only source-touching acquisition command is M-1, whose option string always begins with `ro` and always contains `norecover`.
2. Read-only is **verified after the fact** against both the kernel mount table and `statvfs`; a writable mount is torn down and reported, never used.
3. `uid`/`gid`/`umask=077` restrict presentation to the invoking desktop user (SRS §3.8, ADR-18).
4. Elevation is used for exactly three operations: mount, unmount, and (in `manifest_generator`, not here) `ntfsls`. Directory creation/removal is unprivileged.
5. Unmounting a pre-existing host mount may cause the **host kernel** to flush its own pending writes. The application issues no write syscalls; the confirmation message must not promise otherwise. This residual behaviour is disclosed, not hidden.
6. No retry of any source-touching command is performed, ever.

## 6. Threading and cancellation

1. `MountManager` is a stateful, thread-safe class (ADR-16). Internal state: tracked mounts, unreleased outcomes, cached elevation probe, per-source operation locks — all guarded by a single `threading.RLock` (`_state_lock`).
2. `_state_lock` is **never held across a subprocess call or a confirmation callback**. It is held only for short state reads/mutations. A per-source operation lock serialises `prepare_source`/`release_source` for the same `source_id`; different sources may proceed concurrently.
3. Blocking methods (`list_block_devices`, `probe_elevation`, `prime_elevation`, `prepare_source`, `release_source`, `release_all`, `release_orphan`, `sweep_orphans`) shall run on coordinator worker threads, never on the Tk thread (ADR-4, SDD §2.19). The three accessors in §2.11 are Tk-thread safe.
4. Confirmation callbacks execute on the calling worker thread and may block. This module imposes no timeout on them; the coordinator guarantees a bounded, cancellation-aware wait (ADR-23). Because no lock is held during the callback, the callback may safely call `unreleased_mounts()` or `mount_point_for()` re-entrantly.
5. Cancellation is cooperative (ADR-15) with the checkpoints listed in §2.6.21. `prepare_source` is a resource-acquisition transaction, so cancellation raises `PreparationCancelled` **after rollback** rather than returning a half-prepared source (§9.1 DEV-2). `prime_elevation` returns normally with `cancelled=True`.
6. Release paths accept no cancel event and always run to completion.
7. Subprocesses are started with `start_new_session=True`; on timeout or cancellation the whole process group is signalled (`SIGTERM`, then `SIGKILL` after a bounded grace period), and the mount table is re-read to establish the true post-condition. A mount that appeared after a timeout is tracked and reported, never leaked.
8. No method is async-signal-safe. `main.py` shall invoke `release_all()` from the normal main-thread shutdown path (or `root.after`), not directly from a signal handler.
9. The module holds no database connection, no Tk widget, and no queue reference.

## 7. Non-contract internals (free to vary)

- All `_`-prefixed helpers: `_run_host`, `_run_privileged`, `_resolve_binary`, `_parse_lsblk_json`, `_iter_mountinfo`, `_device_identity`, `_matching_mounts`, `_classify_mount_failure`, `_classify_umount_failure`, `_ensure_elevation`, `_assert_safe_mountpoint`, `_kill_process_group`, `_LOG`.
- Private constants, including `_CRITICAL_ERRNOS`, stderr pattern tables, binary candidate lists, mount-point mode constant, poll intervals, and the `SIGTERM`→`SIGKILL` grace period. The *semantics* they implement (§2, §3.2) are contract; the symbols and literal regexes are not.
- Exact exception, warning, log, and confirmation wording (required content elements are contract).
- Natural-sort implementation, JSON coercion helpers, escape-decoding implementation.
- Internal dict/lock bookkeeping and the mechanism (not the existence or bound) of the single `lsblk` column fallback.
- Import spelling (`from models import …` vs `from src.models import …`) and `__future__` usage.
- Dataclass-generated dunders; `__init__`/`__enter__`/`__exit__` bodies (underscore-prefixed, excluded from the mechanical check in both directions).

## 8. Acceptance fixtures

`tests/test_mount_manager.py` — no root, no live drives, no real subprocesses (NFR-10). An autouse fixture patches `subprocess.Popen` to raise unless a test explicitly installs a fake runner, and patches `os.geteuid`/`os.getegid` to `1000`; `/proc/self/mountinfo` is served from fixture text via a private-seam injection point.

**Option vector**
1. `test_safe_mount_options_exact_vector` — §2.1.1 golden string.
2. `test_forbidden_options_disjoint_and_never_emitted` — including `uid=0`, and across every failure path.
3. `test_build_options_rejects_negative_ids`
4. `test_hibernation_and_repair_tokens_absent` — `remove_hiberfile`, `recover`, `force`, `rw`.
5. `test_hidden_file_hiding_tokens_absent` — protects `NTUSER.DAT` discovery.

**Discovery**
6. `test_lsblk_columns_requested_explicitly`
7. `test_parse_plural_mountpoints`
8. `test_parse_singular_mountpoint_only`
9. `test_parse_mixed_and_escaped_mountpoints` (`\x20`, `\040`)
10. `test_null_and_string_sizes_coerced`
11. `test_whole_disk_ntfs_without_children_accepted`
12. `test_whole_disk_ntfs_with_children_rejected`
13. `test_loop_rom_lvm_crypt_raid_excluded`
14. `test_bitlocker_squashfs_iso_swap_excluded`
15. `test_child_count_counts_unfiltered_children`
16. `test_deterministic_natural_sort_order`
17. `test_duplicate_device_paths_deduplicated`
18. `test_missing_binary_raises_device_enumeration_error`
19. `test_malformed_json_raises_device_enumeration_error`
20. `test_timeout_raises_device_enumeration_error_not_critical`
21. `test_unknown_column_triggers_exactly_one_fallback`
22. `test_other_failure_never_triggers_fallback`
23. `test_no_candidate_returns_empty_list`
24. `test_discovery_never_probes_devices` — forbidden-binary assertion (§5.3).

**Elevation**
25. `test_probe_ready_on_zero_exit`
26. `test_probe_needs_terminal_on_nonzero_exit`
27. `test_probe_unavailable_when_sudo_missing`
28. `test_probe_unavailable_when_root`
29. `test_prime_inherits_stdio`
30. `test_prime_timeout_returns_needs_terminal`
31. `test_prime_cancel_terminates_group_and_returns_cancelled`
32. `test_no_sudo_s_no_pkexec_no_shell`

**Preparation — manifest branch**
33. `test_manifest_prepare_requires_no_elevation`
34. `test_manifest_missing_file_raises_preparation_error`
35. `test_manifest_directory_rejected`
36. `test_manifest_inside_managed_mount_rejected`
37. `test_manifest_empty_file_accepted`
38. `test_manifest_logical_drive_propagated`

**Preparation — mounted branch**
39. `test_logical_drive_none_raises_value_error`
40. `test_unsafe_source_id_raises_value_error`
41. `test_non_block_device_rejected`
42. `test_same_device_second_source_rejected`
43. `test_external_mount_declined_aborts_without_unmount`
44. `test_external_mount_no_callback_aborts`
45. `test_external_mount_approved_normal_unmount_then_mount`
46. `test_busy_then_lazy_declined_aborts`
47. `test_busy_then_lazy_approved_uses_l_flag`
48. `test_protected_mount_point_never_unmounted`
49. `test_ancestor_of_base_never_unmounted`
50. `test_foreign_fstype_match_refused`
51. `test_fuseblk_source_string_matching`
52. `test_mountpoint_created_0700_and_unprivileged`
53. `test_mount_argv_matches_allowlist_exactly`
54. `test_post_mount_rw_mount_torn_down_raises_unsafe_mount_error`
55. `test_statvfs_writable_raises_unsafe_mount_error`
56. `test_eio_stderr_raises_critical_io_error_with_device`
57. `test_mount_timeout_raises_critical_io_error`
58. `test_hibernated_refusal_raises_preparation_error`
59. `test_sudo_password_required_raises_elevation_error`
60. `test_unknown_option_is_not_critical`
61. `test_no_retry_after_any_mount_failure`
62. `test_tracking_registered_before_mount_command`
63. `test_idempotent_reprepare_issues_no_commands`

**Cancellation**
64. `test_cancel_before_mount_raises_preparation_cancelled`
65. `test_cancel_after_mount_rolls_back_and_untracks`
66. `test_cancel_during_confirmation_callback_rolls_back`
67. `test_cancel_never_leaks_mountpoint_directory`

**Release**
68. `test_release_unknown_id_is_not_tracked`
69. `test_release_is_idempotent`
70. `test_release_busy_without_callback_is_busy_and_retained`
71. `test_release_busy_declined_is_declined_and_retained`
72. `test_release_busy_approved_is_released_lazy`
73. `test_release_failure_never_raises`
74. `test_release_timeout_is_failed_not_critical`
75. `test_release_all_order_and_partial_failure`
76. `test_unreleased_mounts_cleared_on_later_success`
77. `test_rmdir_only_after_unmount_verified`
78. `test_no_rmtree_anywhere` — source-tree assertion.

**Orphans, base dir, concurrency**
79. `test_sweep_detects_only_mounted_owned_children`
80. `test_sweep_performs_no_unmount`
81. `test_sweep_excludes_tracked_mounts`
82. `test_release_orphan_outside_base_is_not_tracked`
83. `test_base_under_media_rejected`
84. `test_base_on_ntfs_mount_rejected`
85. `test_base_mode_tightened_never_loosened`
86. `test_base_relative_path_raises_value_error`
87. `test_state_lock_not_held_during_subprocess`
88. `test_callback_may_call_accessors_reentrantly`
89. `test_concurrent_prepare_distinct_sources`
90. `test_accessors_return_immutable_snapshots`

Contract drift: `tests/test_contracts.py::test_contract_sheet[mount_manager.md]` activates on promotion. Refresh collection (`pytest --collect-only`) after freezing; IDE explorers cache collection results.

## 9. Deviations from SDD, verification obligations, amendment record

### 9.1 Deviations requiring explicit reviewer disposition

| ID | Deviation | Rationale | Disposition |
|---|---|---|---|
| DEV-1 | `release_source` returns `ReleaseOutcome` and `release_all` returns `tuple[ReleaseOutcome, ...]`; SDD §2.7 declares `-> None`. Additive `release_orphan()` and three non-blocking accessors. | SDD itself requires the busy/no-callback case to "leave mounted, record for startup sweep". A structured return makes that record observable without a mutable side-channel drain, lets the coordinator emit precise per-source warnings, and keeps cleanup exception-free. `release_orphan` is the missing actuator for the ADR-18 startup sweep — `sweep_orphans` detects but SDD provides no way to release an untracked mount. | CONTRACTUAL — amend SDD §2.7 signature block at freeze. |
| DEV-2 | `prepare_source` gains keyword-only `confirm_lazy` and `cancel_event`; cancellation raises `PreparationCancelled` after rollback rather than returning normally. | (a) SDD's single `confirm_unmount` callback cannot distinguish the *second*, lazy confirmation from the first without prose-sniffing; a separate `confirm_lazy` parameter preserves the published two-argument `UnmountConfirmCallback` alias verbatim while letting the coordinator bind each closure to the correct `ConfirmationKind` (ADR-23). (b) ADR-15's "return normally" rule is written for producer/iterator stages; an acquisition transaction cannot return a half-prepared `PreparedSource`, which has no status field. Rollback-then-raise is the only leak-free option. | CONTRACTUAL — amend SDD §2.7; note the ADR-15 scope clarification in §9.2. |
| DEV-3 | Mount-point directories are created and removed **unprivileged** (owner `0700`), not by the privileged process. | SDD §4.1 ("owned by the privileged acquisition process") and SRS §3.7 (elevation for creating/removing temp mount dirs) conflict with ADR-18 (`0700`, owner-only, under the user's state home). Root-created `0700` directories under `$HOME` would be untraversable by the desktop user, defeating the mount. Elevation is therefore narrowed to mount/umount only — strictly less privilege, same guarantee. | CONTRACTUAL — amend SDD §4.1 and SRS §3.7 bullet list. |
| DEV-4 | The mount option vector is `ro,norecover,noatime,nodev,nosuid,noexec,streams_interface=none,uid=…,gid=…,umask=077`. The review shorthand `ro,ro_dirty` is rejected. | `ro_dirty` is not an option recognised by `ntfs-3g`; freezing it would abort **every** mount on the target platform, i.e. the entire dirty-volume use case. Its intent is fully realised by `ro` (kernel read-only, dirty volumes accepted) plus `norecover` (no journal replay, no dirty-bit clearing, no hibernation-file removal). | INTERNAL (documentation shorthand corrected); reviewer must confirm §9.3 V-1. |
| DEV-5 | Privileged commands use `sudo -n -- <abs_cmd> …`; ADR-14 shows plain `sudo <abs_cmd> …`. | After `prime_elevation`, `-n` guarantees a worker can never block on an invisible password prompt; an expired cache fails fast as `ElevationError` and the coordinator re-primes. `--` terminates sudo's own option parsing. Both are strict narrowings of the ADR-14 allowlist. | CONTRACTUAL — record the hardened vector in ADR-14 at freeze. |
| DEV-6 | `sweep_orphans` reads `/proc/self/mountinfo`; ADR-18 names `/proc/mounts`. | `mountinfo` is the machine-readable superset: it exposes per-mount `ro`/`rw` flags, `major:minor`, and the mount source, all of which the read-only assertion and fuseblk device matching require. Same information, no additional access. | INTERNAL — clarification note in ADR-18. |
| DEV-7 | Constructor gains keyword-only timeout parameters. | Bounded execution (§6.7) must be tunable for tests and for slow USB media without editing frozen constants. The SDD call form `MountManager(base_mount_dir)` remains valid. | INTERNAL — additive, defaults preserve SDD behaviour. |

### 9.2 Residual risks disclosed (not defects)

1. **Mount-namespace scope.** `/proc/self/mountinfo` describes the calling namespace. A desktop automounter operating in a different mount namespace would be invisible. On the supported Ubuntu 24.04 desktop this does not occur; the limitation is recorded rather than papered over with a heuristic.
2. **Host flush on unmount.** Closing a pre-existing writable host mount may flush that driver's pending writes (§5.4.5). The application cannot prevent this and issues no writes itself; the alternative (leaving a writable mount on a damaged volume) is worse.
3. **Irreversible external unmount on cancellation** (§2.6.23). The coordinator must warn; the contract does not promise restoration.
4. **Cold udev metadata.** A device never probed by udev presents no `FSTYPE` and is not offered as a candidate. The module deliberately refuses to probe it (§2.3.8); the user-facing remedy is to let the desktop settle or use manifest generation, not to read the drive.
5. **Shared sudo helper duplication.** `manifest_generator` also needs privileged execution but may not depend on `mount_manager` (`src/README.md` §1.2). Each module therefore carries private `_run_privileged`/`_resolve_binary` helpers. This duplication is intentional and Tier 2; extracting a shared elevation module would be a Tier 0 dependency-graph amendment.

### 9.3 Freeze-gate verification obligations (must pass before promotion)

| ID | Verification | Method | Failure consequence |
|---|---|---|---|
| V-1 | Every token in `SAFE_MOUNT_OPTIONS` is accepted by the pinned `ntfs-3g` (Ubuntu 24.04: `2022.10.3`), and the resulting mount is `ro` per both mount table and `statvfs`, on a **dirty** and on a **hibernated** fixture volume. | Manual, one-off, on a disposable image; recorded in the freeze commit message. | Amend §1/§2.1 (minor bump) before freeze. The implementation shall never silently drop a token. |
| V-2 | `ntfs-3g` accepts the positional form `<device> <mountpoint>` after `-o <opts>` with no `--`, and rejects nothing in the vector as an unknown option. | Same run as V-1. | Amend §5.2 M-1. |
| V-3 | `lsblk` from `util-linux 2.39` accepts all of `LSBLK_COLUMNS`, including both `MOUNTPOINT` and `MOUNTPOINTS`, with `--json --bytes --paths`. | Host command, no drive access. | Reduce `LSBLK_COLUMNS` to the fallback set and amend §1. |
| V-4 | `umount` and `sudo` resolve to the documented absolute candidates on a merged-`/usr` Ubuntu 24.04 Live session. | Host inspection. | Amend candidate lists (Tier 2) and re-run §8 fixtures. |
| V-5 | No frozen symbol collides with the mechanical checker: the module logger is `_LOG`; every public symbol in the source appears in §1 and vice versa. | `pytest tests/test_contracts.py --collect-only` then the contract test. | Fix the fence or the source before promotion. |

### 9.4 Obligations created for downstream sheets

- `mount_manager` DRAFT → FROZEN triggers generation of `src/mount_manager.py` and `tests/test_mount_manager.py`.
- `coordinator.md` (DRAFT) must bind two distinct closures for `confirm_unmount` / `confirm_lazy`, map them to `ConfirmationKind.UNMOUNT_EXTERNAL` / `LAZY_UNMOUNT`, own the cancellation-aware wait, call `probe_elevation` → dialog → `prime_elevation` once per scan start, and translate §4's table without adding event types.
- `main.md` (DRAFT) must construct `MountManager(<base>/mounts)`, call `sweep_orphans()` at startup, and register `release_all()` on the normal shutdown path (not a signal handler).
- No Tier 0 change is requested: `models` v1.1.0, `pathnorm`, `config/*`, and the DDD schema are untouched; `SCHEMA_VERSION` does not move.

### 9.5 Amendment record

| Version | Date | Change | Rationale | Approved by |
|---|---|---|---|---|
| 1.0.0 | 2026-11-17 | Initial DRAFT of the `mount_manager` public surface, error taxonomy, I/O allowlist, and threading contract. | Phase 2 rolling freeze: `db.py` is being generated against frozen `db.md`; this sheet fixes the acquisition seam so `mount_manager.py` can be generated on local hardware while `db.py` is under review. Deviations DEV-1…DEV-7 recorded, never silent. | Pending — Reviewer ______ · Coordinator ______ |

**Reviewer checklist for promotion:** ☐ DEV-1 … ☐ DEV-7 dispositioned ☐ V-1 … V-5 evidence attached ☐ §1 fence matches the intended implementation surface ☐ §5.3 forbidden-command list accepted ☐ §2.6.18 read-only assertion accepted as fatal ☐ SDD/SRS/ADR doc amendments queued as CONTRACTUAL fixes.