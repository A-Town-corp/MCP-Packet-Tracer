# infrastructure/persistence/

Project persistence - save, load, and list topologies on disk.

## Files

### `project_repository.py` - Project repository

Manages the persistence of plans and metadata on the filesystem.

```python
class ProjectRepository:
    def __init__(base_dir="projects")
    def save_plan(plan, project_name) -> Path
    def load_plan(project_name) -> TopologyPlan
    def list_projects() -> list[dict]
    def delete_project(project_name) -> bool
```

**Structure of a saved project:**
```
projects/
+-- mi_topologia/
    +-- plan.json        <- TopologyPlan serializado (Pydantic JSON)
    +-- metadata.json    <- Metadata del proyecto
```

**Methods:**

| Method | Description |
|--------|-------------|
| `save_plan(plan, name)` | Serializes the plan as JSON + generates metadata (name, date, counts, is_valid) |
| `load_plan(name)` | Deserializes JSON -> `TopologyPlan` via `model_validate_json()` |
| `list_projects()` | Scans the base directory, returns a list of metadata per project |
| `delete_project(name)` | Deletes the entire project directory (`shutil.rmtree`) |

**Generated metadata:**
```json
{
  "project_name": "mi_topologia",
  "created_at": "2026-03-25T10:00:00+00:00",
  "devices": 8,
  "links": 7,
  "is_valid": true
}
```

**Note:** The default base directory is `projects/` relative to the server's CWD. The MCP tools `pt_list_projects` and `pt_load_project` use this repository directly.
