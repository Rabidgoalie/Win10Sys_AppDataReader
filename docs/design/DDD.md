# Database Design Document (DDD): Windows 10 Disaster Recovery Application

## 1. Architecture Overview & Storage Strategy
The application utilizes a lightweight, file-based persistence strategy leveraging SQLite for active session caching and structured JSON for portable snapshot exports. This ensures zero external database server dependency while maintaining ACID compliance and efficient querying over parsed registry keys and heuristic save directories.

```
┌────────────────────────────────────────────────────────┐
│               Data Ingestion & Parsing                 │
│  (Offline Registry Hives & ntfsls Text Manifests)      │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│              SQLite In-Memory / Local DB               │
│  ├── AppRecords (Installed Apps Metadata)              │
│  ├── RegistryHives (SOFTWARE / SYSTEM keys)            │
│  └── HeuristicSaves (Discovered Local Save Paths)      │
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│               Snapshot Export Manager                  │
│  └── Portable JSON / SQLite Dump (Viewer Mode)         │
└────────────────────────────────────────────────────────┘
```

## 2. Logical Data Model (Entity-Relationship Diagram)
Using Crow's Foot notation to represent cardinality and participation:

```
[ SCAN_SESSION ] 1 ||------o< [ APP_RECORD ]
                                  |
                                  |--< 1 o------o< [ REGISTRY_KEY ]
                                  |
                                  |--< 1 o------o< [ HEURISTIC_SAVE ]
```

### Entity Descriptions & Relationships
* **`SCAN_SESSION`**: Represents a single disaster recovery execution pointing to a specific source drive/partition or pre-existing manifest file.
* **`APP_RECORD`**: Represents an inventory item discovered from the unbootable partition or NTFS manifest.
* **`REGISTRY_KEY`**: Maps offline registry entries (`SOFTWARE`, `SYSTEM`) correlated to an application record.
* **`HEURISTIC_SAVE`**: Stores identified local save folders, profile paths, and confidence ratings discovered during traversal.

## 3. Data Dictionary

### Table: `SCAN_SESSION`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `session_id` | VARCHAR(36) | PRIMARY KEY, UUID | Unique identifier for the recovery scan session. |
| `source_path` | TEXT | NOT NULL | Path to raw partition (`/dev/sdd1`) or manifest file. |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Timestamp when the scan or snapshot was initialized. |
| `mode` | VARCHAR(20) | CHECK (`mode` IN ('active', 'viewer')) | Operating mode of the session. |

### Table: `APP_RECORD`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `app_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Internal surrogate key for the application. |
| `session_id` | VARCHAR(36) | FOREIGN KEY (`SCAN_SESSION`), NOT NULL | Parent scan session reference. |
| `app_name` | VARCHAR(255) | NOT NULL | Display name of the installed application. |
| `install_path` | TEXT | NULLABLE | Absolute path on the source partition. |
| `version` | VARCHAR(64) | NULLABLE | Software version extracted from manifest/registry. |
| `registry_status` | VARCHAR(32) | CHECK (`registry_status` IN ('Verified', 'Orphaned', 'Unknown')) | Correlation status with offline registry hives. |

### Table: `REGISTRY_KEY`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `key_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Internal surrogate key. |
| `app_id` | INTEGER | FOREIGN KEY (`APP_RECORD`), NOT NULL | Associated application record. |
| `hive_name` | VARCHAR(64) | NOT NULL | Source hive (`SOFTWARE` or `SYSTEM`). |
| `registry_path` | TEXT | NOT NULL | Full path of the registry key. |

### Table: `HEURISTIC_SAVE`
| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `save_id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Internal surrogate key. |
| `app_id` | INTEGER | FOREIGN KEY (`APP_RECORD`), NOT NULL | Associated application record. |
| `save_path` | TEXT | NOT NULL | Discovered directory path containing save files. |
| `nomenclature_match` | VARCHAR(128) | NOT NULL | Heuristic pattern matched (`saves`, `profiles`, etc.). |
| `severity_level` | VARCHAR(16) | CHECK (`severity_level` IN ('Low', 'Medium', 'High')) | Warning indicator for user data risk. |

## 4. Indexing Strategy & Performance Considerations
* **Index 1 (`idx_app_session`)**: `CREATE INDEX idx_app_session ON APP_RECORD(session_id);` — Optimizes lookups when rendering treeviews in the Tkinter GUI.
* **Index 2 (`idx_heuristic_app`)**: `CREATE INDEX idx_heuristic_app ON HEURISTIC_SAVE(app_id);` — Ensures fast retrieval of warning indicators without full table scans.