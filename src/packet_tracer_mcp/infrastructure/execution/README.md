# infrastructure/execution/

Topology deployment strategies. They implement different ways of taking a `TopologyPlan` to Packet Tracer or to disk.

## Architecture

```
ExecutorBase (ABC)
+-- ManualExecutor    -> Exports files to disk
+-- DeployExecutor    -> Exports + copies to clipboard + instructions
+-- LiveExecutor      -> Sends commands in real time via the HTTP bridge
     +-- PTCommandBridge -> Local HTTP server (port 54321)
```

## Files

### `executor_base.py` - Abstract base class

```python
class ExecutorBase(ABC):
    def execute(plan, project_name) -> dict    # Abstract
    def is_available() -> bool                  # Abstract
```

Contract that all executors must fulfill.

---

### `manual_executor.py` - Export to disk

Exports all plan artifacts as files to the filesystem.

```python
class ManualExecutor(ExecutorBase):
    def execute(plan, project_name) -> dict
    def is_available() -> True  # Siempre disponible
```

**Generated files:**
| File | Content |
|---------|-----------|
| `topology.js` | Basic PTBuilder script (addDevice + addLink) |
| `full_build.js` | Full script with configurations |
| `{Device}_config.txt` | CLI config per device (R1, SW1, etc.) |
| `plan.json` | Full serialized plan |
| `metadata.json` | Project metadata (name, date, counts) |

---

### `deploy_executor.py` - Deployment with clipboard

Extends the export-to-disk by adding clipboard copy and step-by-step instruction generation.

```python
class DeployExecutor(ExecutorBase):
    def __init__(output_dir="projects")
    def execute(plan, project_name) -> dict
```

**Flow:**
1. Generates scripts and configs (same as ManualExecutor)
2. Copies `topology.js` to the clipboard (Windows only, via `clip.exe`)
3. Saves all files to disk
4. Generates step-by-step instructions for the user

**Note:** The clipboard function works on Windows only. On macOS/Linux, the files are exported but the clipboard step is skipped.

---

### `live_bridge.py` - HTTP Bridge for Packet Tracer (~300 lines)

Local HTTP server that enables bidirectional communication between Python and Packet Tracer in real time.

```python
class PTCommandBridge:
    def __init__(port=54321)
    def start() -> None
    def send(js_code) -> bool
    def send_and_wait(js_code, timeout) -> str | None
    def bootstrap_script() -> str
    @property
    def is_connected -> bool
```

**HTTP endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/next` | PTBuilder polling - returns the next JS command from the queue |
| `GET` | `/ping` | Basic health check |
| `GET` | `/status` | Detailed bridge status |
| `POST` | `/result` | PTBuilder sends an execution result |
| `POST` | `/queue` | Enqueues a JS command externally |

**Design:**
```
Python (PTCommandBridge)         PT Builder (QWebEngine)
       v                              v
  POST /queue ---> cola ------> GET /next (polling 500ms)
                                       v
                               $se('runCode', cmd)
                                       v
                               POST /result ---> callback
```

**Bootstrap:** One-liner JS pasted into the PT Builder Code Editor:
```javascript
window.webview.evaluateJavaScriptAsync("setInterval(function(){...},500)");
```

---

### `live_executor.py` - Real-time execution

Uses the bridge to send the plan's commands directly to a running PT.

```python
class LiveExecutor:
    def execute(plan, delay=500) -> dict
```

Converts `TopologyPlan` -> JS command sequence -> sends via `PTCommandBridge` with a configurable delay between each command.
