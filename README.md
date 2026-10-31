# Windows 10 Disaster Recovery Application

A secure, non-destructive desktop utility designed to assist users recovering from catastrophic "Inaccessible Boot Device" BSOD failures. It inventories installed applications from unbootable Windows partitions and secondary NTFS drives, identifies local user save directories using heuristics, and presents findings in an empathetic Tkinter GUI dashboard.

> **Important Disclaimer on User File Discovery:** While the application utilizes advanced heuristic scanning to locate common user save directories and profile nomenclature (`saves`, `profiles`, `.db`, etc.) within application folders, _**it cannot guarantee the absolute recovery of every user-generated file**_. Custom save locations or non-standard directory structures may require manual user verification. Users should treat scan results as a supportive discovery aid rather than an exhaustive backup guarantee.

The application does _**not**_ do any actual backups of any kind, as this would require "write" privilages that are intentionally avoided to reduce risk to user files and file system integrity. It is meant solely as a discovery tool to help find irreplacable user-created content that might be lost otherwise.

---

## Key Features & Architecture
* **Non-Destructive NTFS Parsing:** Bypasses kernel mount restrictions on "dirty" volumes via `ntfsls` (`ADR-1`, `FR-1`).
* **Forced Read-Only Isolation:** Automatically checks raw block devices via `lsblk`, programmatically force-unmounts native `ntfs3` mounts (`sudo umount -l`), and securely mounts to `/tmp/win10_recovery` using `ntfs-3g` with `-o ro,ro_dirty` (`ADR-5`).
* **Offline Registry Correlation:** Reads offline Windows `SOFTWARE` and `SYSTEM` hives to verify installation status (`FR-2`).
* **Heuristic Save Detection:** Automatically flags user profile folders and save directories (`saves`, `profiles`, `.db`) with severity indicators (`FR-3`, `NFR-2`). Note that while heuristics assist in identifying common save nomenclature, the application cannot guarantee 100% discovery of all user-generated files across custom application directories.
* **Snapshot Export & Viewer Mode:** Serializes session findings into portable JSON/SQLite reports, locking the UI into read-only viewer mode (`FR-5`, `ADR-3`, `DDD.md`).
* **Thread-Safe UI Dashboard:** Decouples background ingestion workers from the Tkinter GUI via `queue.Queue` to maintain 60 FPS responsiveness (`NFR-1`, `ADR-4`, `SDD.md`).

---

## Quick Start & Installation

The application supports two primary deployment modes managed by the unified bootstrap script (`ADR-2`, `SDD.md`): an ephemeral **Ubuntu 24.04 Live USB Session** ("Try Ubuntu") and an **Advanced Conda Environment** for host systems.

### Option A: Ubuntu 24.04 Live USB Session (Recommended for Disaster Recovery)
*Note: In accordance with `ADR-2`, `./setup.sh` will never modify system packages automatically or prompt for blind approvals. If any host utilities (such as `python3-venv` or `ntfs-3g`) are missing, the script will output clear, manual commands and exit safely.*

1. **Clone Repository & Bootstrap:**
   ```bash
   git clone https://github.com/Rabidgoalie/Win10Sys_AppDataReader.git
   cd win10-disaster-recovery
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Run the Application:**
   ```bash
   python src/main.py
   ```

### Option B: Advanced Conda Environment (For Developers / Host Systems)
*Note: If running on a development workstation, activate your isolated Conda environment (Python 3.12.3) before executing `./setup.sh`. In accordance with `ADR-2`, the bootstrap script strictly avoids automatic host package modifications and will pause with manual instructions if required tools (like `ntfs-3g`) are absent.*

1. **Create and Activate Conda Environment (Python 3.12.3):**
   ```bash
   conda create -n win10-recovery python=3.12.3
   conda activate win10-recovery
   ```

2. **Clone Repository and Run Bootstrap:**
   ```bash
   git clone https://github.com/Rabidgoalie/Win10Sys_AppDataReader.git
   cd win10-disaster-recovery
   chmod +x setup.sh
   ./setup.sh
   ```

3. **Run the Application:**
   ```bash
   python src/main.py
   ```

---

## Project Documentation
* **SRS:** [Software Requirements Specification](docs/design/SRS.md)
* **SDD:** [Software Design Document](docs/design/SDD.md)
* **DDD:** [Database Design Document](docs/design/DDD.md)
* **UIDD:** [UI/UX Design Document](docs/design/UIDD.md)
* **ADRs:** [Architecture Decision Records](docs/ADR.md)