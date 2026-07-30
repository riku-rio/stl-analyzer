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
