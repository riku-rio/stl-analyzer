# STL Analyzer Error Codes

Domain error codes are stable identifiers intended for automation. They are independent from the broader process exit-code classes.

## Process exit codes

| Exit code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Unexpected internal error |
| 2 | Invalid CLI usage |
| 3 | Configuration or workspace error |
| 4 | Invalid case or source STL |
| 5 | Blender inspection or rendering failure |
| 6 | Invalid workflow state or schema document |
| 7 | Quality threshold not met within the iteration limit |
| 8 | Partial multi-case command failure |

## Batch A domain errors

| Code | Exit code | Meaning |
|---|---:|---|
| `INTERNAL_ERROR` | 1 | An unexpected exception reached the command boundary. |
| `TARGET_NOT_DIRECTORY` | 3 | The requested initialization target is an existing non-directory path. |
| `UNSAFE_PATH` | 3 | A path escaped or violated its approved root. |
| `INIT_CONFLICT` | 3 | Preflight found one or more conflicts and performed no writes. |
| `INIT_COMMIT_FAILED` | 3 | A commit-stage filesystem operation failed and rollback was attempted. |

## Batch B domain errors

| Code | Exit code | Meaning |
|---|---:|---|
| `WORKSPACE_NOT_FOUND` | 3 | Run outside an initialized stl-analyzer workspace. |
| `CONFIG_MISSING` | 3 | Configuration file is missing. |
| `CONFIG_PARSE_ERROR` | 3 | Configuration file contains invalid TOML. |
| `CONFIG_VALIDATION_ERROR` | 3 | Configuration file schema validation failed. |
| `INVALID_CASE_ID` | 4 | Provided case ID is invalid or contains traversal. |
| `CASE_NOT_FOUND` | 4 | The specified case does not exist. |
| `UNREADABLE_CASE` | 4 | Case directory could not be read. |
| `NO_STL_FOUND` | 4 | Case directory does not contain any valid STL files. |
| `MULTIPLE_STL_FILES` | 4 | Case directory contains multiple STL files. |
| `UNREADABLE_STL` | 4 | The STL file could not be read. |
| `INVALID_ASSETS_PATH` | 3 | Assets path config resolves outside case directory. |
| `CASE_NOT_WRITABLE` | 3 | Cannot write to the case directory. |
| `BLENDER_NOT_FOUND` | 5 | Blender executable was not found. |
| `BLENDER_INVOCATION_FAILED` | 5 | Blender subprocess invocation failed entirely. |

Expected failures use the common JSON envelope:

```json
{
  "success": false,
  "error": {
    "code": "INIT_CONFLICT",
    "message": "Workspace initialization found conflicts and made no changes.",
    "details": {},
    "recoverable": true,
    "suggested_action": "Resolve the reported conflicts and run init again."
  }
}
```
