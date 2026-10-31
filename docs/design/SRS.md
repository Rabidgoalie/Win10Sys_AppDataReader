# Software Requirements Specification (SRS): Windows 10 Disaster Recovery Application

## 1. Introduction & Objectives
The Windows 10 Disaster Recovery Application is a desktop utility designed to assist users recovering from catastrophic "Inaccessible Boot Device" BSOD failures. It non-destructively inventories installed applications from an unbootable Windows partition and a secondary NTFS drive (handled via raw device parsing to bypass dirty-bit restrictions), identifies potential local user save directories using heuristics, and presents the findings in an empathetic, easy-to-navigate Tkinter GUI.

## 2. Scope & Constraints
* **Non-Destructive Principle:** The application performs strictly read-only operations on source drives and partitions. It never modifies, writes to, or attempts kernel-mounting of dirty NTFS volumes, utilizing programmatic force-unmounting and isolated `ntfs-3g` (`-o ro,ro_dirty`) remounting when necessary per `ADR-5`.
* **Environment Agnostic:** Runs in an isolated Conda environment or an Ubuntu 24.04 Live USB session via a single bootstrap script without polluting host system global packages.
* **Privilege Handling:** Minimal `sudo` usage restricted strictly to querying block devices (`lsblk`), lazy unmounting (`umount -l`), safe read-only remounting (`mount -t ntfs-3g -o ro,ro_dirty`), and invoking `ntfsls -f` when secondary drives cannot be mounted normally.

## 3. Functional Requirements
* **FR-1: Manifest Generation & Drive Discovery:** Enumerate block devices via JSON-formatted `lsblk`, safely unmount and remount dirty partitions via `ntfs-3g` (`ADR-5`), or accept a pre-existing `ntfsls` text manifest file.
* **FR-2: Registry & Manifest Parsing:** Read offline Windows Registry hives (`SOFTWARE`, `SYSTEM`) from the mounted main OS drive and correlate them with the file manifest.
* **FR-3: Heuristic Local Save Detection:** Scan application home folders for common save/profile nomenclature (`saves`, `profiles`, `userdata`, `.db`, etc.) to flag locally stored user data.
* **FR-4: Tkinter GUI Dashboard:** Present a structured, sortable list of applications with columns detailing installation metadata, registry status, and local save indicators.
* **FR-5: Snapshot Export & Viewer Mode:** Enable exporting enumeration results to a structured JSON report (per `DDD.md`) and loading existing reports into a read-only viewer mode to prevent redundant long-running scans.

## 4. Non-Functional Requirements
* **NFR-1: Performance & Responsiveness:** Background threading for directory scanning and parsing to keep the Tkinter UI fully responsive.
* **NFR-2: Usability & Empathy:** Clear status indicators, descriptive error handling, and warning colors (Amber/Red) for detected local saves.
* **NFR-3: Portability:** Packaged with a unified `setup.sh` script supporting both developer Conda and live session workflows.
