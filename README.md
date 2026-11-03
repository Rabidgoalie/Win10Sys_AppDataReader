# Windows 10 Disaster Recovery

A free, MIT-licensed Linux utility designed to help users recover from catastrophic Windows 10 boot failures.

The most important goal of this project is to help users find irreplaceable, self-authored files before reinstalling an operating system or wiping a drive.

> **Important Disclaimer on User File Discovery:** While the application utilizes advanced heuristic scanning to locate common user save directories and profile nomenclature (`saves`, `profiles`, `.db`, etc.) within application folders, _**it cannot guarantee the discovery of every user-generated file**_. Custom save locations or non-standard directory structures may require manual user verification. Users should treat scan results as a supportive discovery aid rather than an exhaustive guarantee.

The application also builds an inventory of installed applications, portable applications, and orphaned application evidence to help users understand what existed on their Windows installation. This will aid the user in reinstalling their applications on a new Windows install, to "restore" their previous computing environment.

## Important Warning

If your Windows 10 system has failed, do not wipe or format drives until you have scanned them. The results of the scan can then be used to manually recover all user-generated data found by the scan, before the installation of an OS. **The application does _not_ recover files for you; you _will_ have to copy these to backup storage media manually.**

If you used secondary drives for programs, games, documents, photos, videos, music, source code, or other personal files, add those drives to the scan as well.

> Once a drive is wiped, data recovery can be very difficult or impossible, outside _very_ expensive data recovery services.

## Recommended Environment

The primary recommended environment is:

- Ubuntu 24.04 Live Session

The application also supports:

- Pop!_OS 24.04
- Ubuntu 24.04-compatible Linux systems

The application requires:

- Python 3.12.3
- `python3-venv`
- Tkinter
- `lsblk`
- `sudo`
- `mount`
- `umount`
- `ntfs-3g` tooling, including `ntfsls`

The application does not require Conda.

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

It will not automatically install host system packages. If host packages are missing, it will explain what to install and why.

## Running the Application

After setup completes:

```bash
source Win10DRBPythonVenv/bin/activate
python src/main.py
```

## Safety Principles

This application is read-only.

It does not:

- Modify scanned drives.
- Write to scanned drives.
- Repair Windows.
- Repair file systems.
- Execute Windows binaries.
- Open file contents.
- Transmit scanned data.
- Use AI classification.
- Require network access during scanning.

## Reports

The application can export a JSON report.

Reports contain paths, evidence, and findings. They do not contain file contents.

Reports can be loaded later in TRIAGE viewer mode, to allow each file/folder to be marked as "Confirmed" (i.e., marked findings are important and should be manually-recovered).