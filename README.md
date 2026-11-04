# Windows 10 Disaster Recovery

A free, MIT-licensed Linux utility designed to help users recover from catastrophic Windows 10 boot failures.

The most important goal of this project is to help users find irreplaceable, self-authored files before reinstalling an operating system or wiping a drive.

> **Important Disclaimer on User File Discovery:** This application uses read-only, metadata-based heuristics—such as file names, directory names, paths, extensions, and file counts—to identify _potential_ locations of user-generated content. It does **not** open or inspect file contents. Findings are advisory only and cannot guarantee the discovery of every user-generated file. Custom save locations or non-standard directory structures may require manual verification. Users should treat scan results as a supportive discovery aid, not an exhaustive guarantee. The final judgment about whether a discovered location contains valuable data always belongs to the user.

The application also builds an inventory of installed applications, portable applications, and orphaned application evidence to help users understand what existed on their Windows installation. This will aid the user in reinstalling their applications on a new Windows install, to "restore" their previous computing environment.

## Important Warning

If your Windows 10 system has failed, do not wipe or format drives until you have scanned them. The results of the scan can then be used to manually recover all user-generated data found by the scan, before the installation of an OS. **The application does _not_ recover files for you; you _will_ have to copy these to backup storage media manually.**

If you used secondary drives for programs, games, documents, photos, videos, music, source code, or other personal files, add those drives to the scan as well.

> Once a drive is wiped, data recovery can be very difficult or impossible, outside _very_ expensive data recovery services.

## Essential Safety Step Before Scanning

Before booting into Linux to use this application, you must verify that your Windows 10 boot failure wasn't caused by a physically dying hard drive. While our software is strictly read-only and designed to "do no harm," running scans on a physically failing drive can cause permanent data loss.

We have written a comprehensive, non-technical, step-by-step guide to help you check your drive health using the built-in Windows Recovery screen.

> **Please read and follow the [Drive Health Guide](DRIVE_HEALTH_GUIDE.md) before proceeding.**

### A Note on USB Drives and Recovery Media

To complete a safe recovery, you will need access to two tools:

1. **Windows Installation Media** (to run the pre-recovery drive health checks if your PC's built-in recovery menu is missing).
2. **Ubuntu 24.04 Live Session Media** (to run this recovery application).

**You do not need to buy or use two separate physical USB thumb drives.** You can simply flash a single USB drive with the Windows Installer first, use it to complete the [Drive Health Guide](DRIVE_HEALTH_GUIDE.md), and then plug that thumb drive into a working computer to overwrite and re-flash it with the Ubuntu 24.04 installer.

## Recommended Environment

The primary recommended environment is:

- Ubuntu 24.04 Live Session

The application also supports:

- Pop!_OS 24.04
- Ubuntu 24.04-compatible Linux systems (best-effort)

The application does not support Windows as a host operating environment.

## Requirements

The application requires:

- Python 3.12-series (>= 3.12.0, < 3.13.0; validated reference: 3.12.3)
- `python3-venv`
- Tkinter
- `lsblk`
- `sudo`
- `umount`
- `ntfs-3g` tooling, including `ntfsls`

A working internet connection is required during initial setup so that `setup.sh` can install Python dependencies into the virtual environment. The application itself does not require network access during scanning, analysis, or report viewing.

The application does not require or reference Conda.

The application does not require `git`.

## Download

Most users should download the project ZIP file and extract it.

Then run:

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` will create a local virtual environment named:

```text
Win10DRBPythonVenv
```

It will not automatically install host system packages. If host packages are missing, it will print clear manual installation instructions and exit.

## Running the Application

After setup completes:

```bash
source Win10DRBPythonVenv/bin/activate
python src/main.py
```

## Safety Principles

This application is strictly read-only toward scanned drives.

It does not:

- Write to scanned drives.
- Modify NTFS metadata.
- Repair file systems.
- Clear dirty bits.
- Replay NTFS transaction logs in a way that modifies source media.
- Remove hibernation files.
- Repair Windows.
- Execute Windows binaries.
- Open, read, or parse file contents.
- Delete, move, or rename files.
- Change permissions on scanned source files.
- Transmit scanned data externally.
- Use AI or machine-learning classification.
- Require network access during scanning.

The application supports only two acquisition methods:

- **ntfs-3g read-only mount** – safe, non-repair mounting for direct hive and filesystem access.
- **ntfsls manifest** – read-only filesystem enumeration producing a manifest file, without mounting.

The application does not support externally mounted paths (e.g., paths mounted by the kernel `ntfs3` driver or desktop auto-mounters).

## Reports

The application can export a structured JSON report.

Reports contain session metadata, sources, user profiles, application records, evidence records, application-to-evidence links, user-data findings, and warnings. They do not contain file contents.

Reports can be loaded later to enter **Triage Mode**, which allows the user to:

- Mark user-data findings as "Confirmed" (meaning the user has verified the finding contains important data that should be manually recovered).
- Add free-text notes to findings (e.g., "Mom's save files – DO NOT DELETE").

Triage state and notes are preserved within the report and restored when the report is loaded again. No drive operations are permitted in Triage Mode.
