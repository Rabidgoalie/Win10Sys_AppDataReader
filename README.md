# Windows 10 Disaster Recovery Application

A secure, non-destructive desktop utility designed to assist users recovering from catastrophic "Inaccessible Boot Device" BSOD failures. It inventories installed applications from unbootable Windows partitions and secondary NTFS drives, identifies local user save directories using heuristics, and presents findings in an empathetic Tkinter GUI dashboard.

---

## Key Features & Architecture
* **Non-Destructive NTFS Parsing:** Bypasses kernel mount restrictions on "dirty" volumes via `ntfsls` (`ADR-1`, `FR-1`).
* **Offline Registry Correlation:** Reads offline Windows `SOFTWARE` and `SYSTEM` hives to verify installation status (`FR-2`).
* **Heuristic Save Detection:** Automatically flags user profile folders and save directories (`saves`, `profiles`, `.db`) with severity indicators (`FR-3`, `NFR-2`).
* **Snapshot Export & Viewer Mode:** Serializes session findings into portable JSON/SQLite reports, locking the UI into read-only viewer mode (`FR-5`, `ADR-3`, `DDD.md`).
* **Thread-Safe UI Dashboard:** Decouples background ingestion workers from the Tkinter GUI via `queue.Queue` to maintain 60 FPS responsiveness (`NFR-1`, `ADR-4`, `SDD.md`).

---

## Quick Start & Installation

The application supports two primary deployment modes managed by the unified bootstrap script (`ADR-2`, `SDD.md`): an ephemeral **Ubuntu 24.04 Live USB Session** ("Try Ubuntu") and an **Advanced Conda Environment** for host systems.

### Option A: Ubuntu 24.04 Live USB Session (Recommended for Disaster Recovery)
*Note: Running `./setup.sh` directly on the host system installs system packages (like `ntfs-3g`) globally, which is safe and intended exclusively for ephemeral Live USB sessions. The `setup.sh` script will prompt you if it determines that any system packages need to be installed.*

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
*Note: If you are running on a permanent host system, do not execute `./setup.sh` on the bare host. Instead, activate your isolated Conda environment (Python 3.12.3) so the script can safely verify prerequisites and install local Python dependencies without polluting global packages. If `setup.sh` determines that it is not running in a Live Session and `ntfs-3g` is missing, you will be prompted to stop execution. No system packages will be installed on your host system unless you approve of this step (we do not recommend this; use an Ubuntu installation USB device to boot into a Live Session in that case).*

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