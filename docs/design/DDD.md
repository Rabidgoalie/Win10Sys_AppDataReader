# Database Design Document (DDD): Windows 10 Disaster Recovery Application

## 1. Storage Strategy

The application uses SQLite for active session persistence and structured JSON for portable report exports.

A report export serializes the full evidence package:

- Session metadata.
- Sources.
- User profiles.
- Application records.
- Evidence records.
- Application-to-evidence links.
- User-data findings.
- Warnings.
- Schema version.

A report import rehydrates those records into a read-only viewer session.

The database does not store file contents.

## 2. Logical Data Model

```text
[ SCAN_SESSION ] 1 ||------o< [ SCAN_SOURCE ]
        |                         |
        |                         |------o< [ DISCOVERY_EVIDENCE ]
        |                         |
        |                         |------o< [ USER_PROFILE ]
        |
        |------o< [ APP_RECORD ]
        |              |
        |              |------o< [ APP_EVIDENCE ] >------o| [ DISCOVERY_EVIDENCE ]
        |              |
        |              |------o< [ USER_DATA_FINDING ]
        |
        |------o< [ USER_DATA_FINDING ]
```

## 3. Entity Descriptions

### `SCAN_SESSION`

Represents one recovery scan session or one loaded report session.

### `SCAN_SOURCE`

Represents one source used in the session.

A source is either:

- A mounted block device prepared by the application.
- A manifest file generated from a block device or supplied by the user.

Externally mounted paths are not supported.

### `USER_PROFILE`

Represents a Windows user profile discovered on a Windows source.

### `APP_RECORD`

Represents a correlated application identity.

### `DISCOVERY_EVIDENCE`

Represents one raw evidence item.

Evidence is first-class. It may be linked to zero, one, or multiple application records through `APP_EVIDENCE`.

### `APP_EVIDENCE`

Links evidence to application records.

### `USER_DATA_FINDING`

Represents a potential user-generated-content location.

Findings may be associated with an application, a user profile, both, or neither.

## 4. Data Dictionary

### Table: `SCAN_SESSION`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| session_id | VARCHAR(36) | PRIMARY KEY | Unique session identifier. |
| schema_version | VARCHAR(16) | NOT NULL | Database/report schema version. |
| created_at | TIMESTAMP | NOT NULL | Session creation time. |
| mode | VARCHAR(20) | NOT NULL, CHECK mode IN ('active', 'triage') | Session mode. |
| status | VARCHAR(20) | NOT NULL, CHECK status IN ('pending', 'running', 'completed', 'failed', 'cancelled') | Session state. |
| scan_options_json | TEXT | NULL | Enabled evidence and heuristic options. |

### Table: `SCAN_SOURCE`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| source_id | VARCHAR(36) | PRIMARY KEY | Unique source identifier. |
| session_id | VARCHAR(36) | FOREIGN KEY to SCAN_SESSION, NOT NULL | Parent session. |
| source_type | VARCHAR(32) | NOT NULL, CHECK source_type IN ('mounted_block_device', 'manifest_file') | Source type. |
| source_role | VARCHAR(32) | NOT NULL, CHECK source_role IN ('windows_os', 'secondary_data') | Source role. |
| origin_device_path | TEXT | NULL | Original block device path, if known. |
| manifest_path | TEXT | NULL | Manifest path when source is a manifest. |
| mount_point | TEXT | NULL | Mount point when source is mounted. |
| fs_type | TEXT | NULL | Filesystem type. |
| label | TEXT | NULL | Volume label. |
| uuid | TEXT | NULL | Volume UUID. |
| size_bytes | INTEGER | NULL | Volume size, if known. |
| acquisition_method | VARCHAR(32) | NOT NULL, CHECK acquisition_method IN ('ntfs3g_ro', 'ntfsls_manifest') | Acquisition method. |
| read_only | INTEGER | NOT NULL, DEFAULT 1, CHECK read_only = 1 | Read-only flag. |
| status | VARCHAR(20) | NOT NULL, CHECK status IN ('pending', 'ready', 'error', 'complete') | Source state. |
| warnings_json | TEXT | NULL | Source warnings. |

Additional source constraints:

```sql
CHECK (
  (source_type = 'mounted_block_device' AND mount_point IS NOT NULL)
  OR
  (source_type = 'manifest_file' AND manifest_path IS NOT NULL)
)
```

```sql
CHECK (
  (source_type = 'mounted_block_device' AND acquisition_method = 'ntfs3g_ro')
  OR
  (source_type = 'manifest_file' AND acquisition_method = 'ntfsls_manifest')
)
```

### Table: `USER_PROFILE`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| profile_id | VARCHAR(36) | PRIMARY KEY | Unique profile identifier. |
| session_id | VARCHAR(36) | FOREIGN KEY to SCAN_SESSION, NOT NULL | Parent session. |
| source_id | VARCHAR(36) | FOREIGN KEY to SCAN_SOURCE, NOT NULL | Windows source containing the profile. |
| username | TEXT | NULL | Profile username. |
| sid | TEXT | NULL | Security identifier, if discovered. |
| profile_path | TEXT | NULL | Logical Windows profile path. |
| normalized_profile_path | TEXT | NULL | Normalized profile path. |
| ntuser_path | TEXT | NULL | Path to `NTUSER.DAT`. |
| usrclass_path | TEXT | NULL | Path to `UsrClass.dat`. |
| documents_path | TEXT | NULL | Resolved Documents path. |
| desktop_path | TEXT | NULL | Resolved Desktop path. |
| downloads_path | TEXT | NULL | Resolved Downloads path. |
| appdata_local_path | TEXT | NULL | AppData Local path. |
| appdata_roaming_path | TEXT | NULL | AppData Roaming path. |
| appdata_locallow_path | TEXT | NULL | AppData LocalLow path. |
| saved_games_path | TEXT | NULL | Saved Games path. |
| source_code_path | TEXT | NULL | Visual Studio source path, if found. |
| is_default_profile | INTEGER | NOT NULL, DEFAULT 0 | Default profile flag. |
| is_system_profile | INTEGER | NOT NULL, DEFAULT 0 | System profile flag. |
| parse_warnings_json | TEXT | NULL | Profile parse warnings. |

### Table: `APP_RECORD`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| app_id | VARCHAR(36) | PRIMARY KEY | Unique application identifier. |
| session_id | VARCHAR(36) | FOREIGN KEY to SCAN_SESSION, NOT NULL | Parent session. |
| identity_hash | VARCHAR(64) | NOT NULL | Deterministic application identity hash. |
| display_name | TEXT | NOT NULL | Display name. |
| publisher | TEXT | NULL | Publisher. |
| version | TEXT | NULL | Version. |
| install_date | TEXT | NULL | Install date, if discovered. |
| architecture | TEXT | NULL | Architecture hint. |
| install_path | TEXT | NULL | Logical install path. |
| normalized_install_path | TEXT | NULL | Normalized install path. |
| discovery_method | TEXT | NOT NULL, CHECK discovery_method IN ('registry', 'filesystem', 'manifest', 'portable', 'correlated') | Primary discovery method. |
| fingerprint_status | TEXT | NOT NULL, CHECK fingerprint_status IN ('Registered', 'PartiallyRegistered', 'Portable', 'Orphaned', 'Unknown') | Registration fingerprint. |
| evidence_confidence | TEXT | NOT NULL, CHECK evidence_confidence IN ('Low', 'Medium', 'High') | Correlation confidence. |
| portable_score | INTEGER | NULL | Optional portable likelihood score. |
| notes_json | TEXT | NULL | Correlation notes and warnings. |
| created_at | TIMESTAMP | NOT NULL | Record creation time. |

Recommended unique constraint:

```sql
UNIQUE(session_id, identity_hash)
```

### Table: `DISCOVERY_EVIDENCE`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| evidence_id | VARCHAR(36) | PRIMARY KEY | Unique evidence identifier. |
| session_id | VARCHAR(36) | FOREIGN KEY to SCAN_SESSION, NOT NULL | Parent session. |
| source_id | VARCHAR(36) | FOREIGN KEY to SCAN_SOURCE, NOT NULL | Source that produced the evidence. |
| evidence_hash | VARCHAR(64) | NOT NULL, UNIQUE | Deterministic evidence identity hash. |
| evidence_type | TEXT | NOT NULL | Evidence category. |
| hive_file_path | TEXT | NULL | Hive file path, for registry evidence. |
| root_hive | TEXT | NULL | Root hive name, for registry evidence. |
| key_path | TEXT | NULL | Registry key path. |
| value_name | TEXT | NULL | Registry value name. |
| value_data | TEXT | NULL | Registry value data. |
| user_sid | TEXT | NULL | User SID, for user-specific evidence. |
| file_path | TEXT | NULL | File or directory path, for filesystem/manifest evidence. |
| normalized_path | TEXT | NULL | Normalized file or directory path. |
| product_code | TEXT | NULL | MSI product code or package identifier, if known. |
| confidence | TEXT | NOT NULL, CHECK confidence IN ('Low', 'Medium', 'High') | Evidence confidence. |
| parse_warning | TEXT | NULL | Parse warning, if any. |
| raw_json | TEXT | NULL | Additional structured evidence data. |

Supported `evidence_type` values include:

```text
REGISTRY_UNINSTALL
REGISTRY_WOW64_UNINSTALL
REGISTRY_APP_PATH
REGISTRY_MSI_PRODUCT
REGISTRY_MSI_USER_DATA
REGISTRY_MSI_UPGRADE_CODE
REGISTRY_SHARED_DLL
REGISTRY_RUN_KEY
REGISTRY_SERVICE
REGISTRY_APPCOMPAT_CACHE
REGISTRY_USERASSIST
REGISTRY_MUICACHE
REGISTRY_COM_CLSID
REGISTRY_PROGID
REGISTRY_FILE_ASSOCIATION
REGISTRY_APPX
REGISTRY_SHELL_EXTENSION
REGISTRY_SHELL_FOLDER
REGISTRY_USER_PATH_HINT
FILE_EXECUTABLE
FILE_PORTABLE_LAYOUT
FILE_SHORTCUT
FILE_APPX_MANIFEST
FILE_SOURCE_CODE_DIR
MANIFEST_ENTRY
```

### Table: `APP_EVIDENCE`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| link_id | INTEGER | PRIMARY KEY, AUTOINCREMENT | Link surrogate key. |
| app_id | VARCHAR(36) | FOREIGN KEY to APP_RECORD, NOT NULL | Application record. |
| evidence_id | VARCHAR(36) | FOREIGN KEY to DISCOVERY_EVIDENCE, NOT NULL | Evidence record. |
| relevance | TEXT | NOT NULL, CHECK relevance IN ('primary', 'supporting', 'weak') | Evidence relevance. |
| created_at | TIMESTAMP | NOT NULL | Link creation time. |

Recommended unique constraint:

```sql
UNIQUE(app_id, evidence_id)
```

### Table: `USER_DATA_FINDING`

| Column Name | Data Type | Constraints | Description |
|---|---|---|---|
| finding_id | VARCHAR(36) | PRIMARY KEY | Unique finding identifier. |
| session_id | VARCHAR(36) | FOREIGN KEY to SCAN_SESSION, NOT NULL | Parent session. |
| source_id | VARCHAR(36) | FOREIGN KEY to SCAN_SOURCE, NOT NULL | Source containing the finding. |
| app_id | VARCHAR(36) | FOREIGN KEY to APP_RECORD, NULL | Associated application, if known. |
| profile_id | VARCHAR(36) | FOREIGN KEY to USER_PROFILE, NULL | Associated user profile, if known. |
| path | TEXT | NOT NULL | Discovered path. |
| normalized_path | TEXT | NOT NULL | Normalized path. |
| location_category | TEXT | NOT NULL | Path category. |
| inside_documents | INTEGER | NULL, CHECK inside_documents IS NULL OR inside_documents IN (0, 1) | Whether path is inside resolved Documents. |
| documents_root | TEXT | NULL | Documents root used for comparison. |
| owner_username | TEXT | NULL | Profile username, if known. |
| nomenclature_match | TEXT | NULL | Matched folder/name pattern. |
| extension_match | TEXT | NULL | Matched extension pattern, if any. |
| file_count | INTEGER | NULL | Number of files, if known. |
| total_size_bytes | INTEGER | NULL | Total size, if known. |
| severity_level | TEXT | NOT NULL, CHECK severity_level IN ('Low', 'Medium', 'High') | Severity. |
| confidence | TEXT | NOT NULL, CHECK confidence IN ('Low', 'Medium', 'High') | Confidence. |
| rationale | TEXT | NOT NULL | Human-readable explanation. |
| created_at | TIMESTAMP | NOT NULL | Finding creation time. |
| user_confirmed | INTEGER | NULL, CHECK user_confirmed IS NULL OR user_confirmed IN (0, 1) | User's triage state: `1` = Confirmed, `0` or `NULL` = Unconfirmed. |
| user_notes | TEXT | NULL | Free-text notes added by the user during triage. |

Supported `location_category` values include:

```text
DOCUMENTS
DESKTOP
DOWNLOADS
PICTURES
MUSIC
VIDEOS
ONEDRIVE
INSTALL_DIR
APPDATA_ROAMING
APPDATA_LOCAL
APPDATA_LOCALLOW
SAVED_GAMES
VIRTUALSTORE
PROGRAMDATA
SECONDARY_DRIVE
PORTABLE_DATA_DIR
SOURCE_CODE
USER_PROFILE_OTHER
UNKNOWN
```

## 5. Evidence Hash Strategy

The `evidence_hash` prevents duplicate evidence rows and avoids reliance on nullable-column unique constraints.

The application shall compute `evidence_hash` deterministically using SHA-256 over canonical evidence identity fields.

Null fields shall be replaced with empty strings.

Windows paths and registry key paths shall be normalized before hashing.

The canonical fields are:

```text
source_id
evidence_type
hive_file_path
root_hive
key_path
value_name
value_data_hash
user_sid
normalized_path
product_code
```

For file and manifest evidence, `normalized_path` is the primary identity field.

For registry evidence, `hive_file_path`, `key_path`, and `value_name` are the primary identity fields.

If `value_data` is present, the hash shall include a SHA-256 hash of the value data rather than the raw value data.

This approach is more collision-resistant than a composite unique constraint involving nullable columns.

## 6. Indexing Strategy

Recommended indexes:

```sql
CREATE INDEX idx_source_session ON SCAN_SOURCE(session_id);
CREATE INDEX idx_profile_session ON USER_PROFILE(session_id);
CREATE INDEX idx_profile_source ON USER_PROFILE(source_id);
CREATE INDEX idx_app_session ON APP_RECORD(session_id);
CREATE INDEX idx_app_session_name ON APP_RECORD(session_id, display_name);
CREATE INDEX idx_evidence_session ON DISCOVERY_EVIDENCE(session_id);
CREATE INDEX idx_evidence_source ON DISCOVERY_EVIDENCE(source_id);
CREATE INDEX idx_evidence_type ON DISCOVERY_EVIDENCE(evidence_type);
CREATE INDEX idx_evidence_hash ON DISCOVERY_EVIDENCE(evidence_hash);
CREATE INDEX idx_app_evidence_app ON APP_EVIDENCE(app_id);
CREATE INDEX idx_app_evidence_evidence ON APP_EVIDENCE(evidence_id);
CREATE INDEX idx_finding_session ON USER_DATA_FINDING(session_id);
CREATE INDEX idx_finding_app ON USER_DATA_FINDING(app_id);
CREATE INDEX idx_finding_profile ON USER_DATA_FINDING(profile_id);
CREATE INDEX idx_finding_source ON USER_DATA_FINDING(source_id);
CREATE INDEX idx_finding_severity ON USER_DATA_FINDING(severity_level);
CREATE INDEX idx_finding_inside_documents ON USER_DATA_FINDING(inside_documents);
```

## 7. Report Export Structure

The JSON report shall include:

```json
{
  "schema_version": "1.0.0",
  "session": {},
  "sources": [],
  "user_profiles": [],
  "applications": [],
  "evidence": [],
  "app_evidence_links": [],
  "user_data_findings": [],
  "warnings": []
}
```

The report shall not include file contents.

Report import shall validate `schema_version` before hydration.

## 8. Concurrency and Transaction Notes

SQLite access shall be serialized through the persistence layer.

Background workers shall not write to the UI directly.

Long-running scans should use periodic transaction commits to avoid excessive memory use.

Foreign key enforcement shall be enabled.