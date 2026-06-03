# packet_tracer_mcp

Main module of the MCP server for Cisco Packet Tracer.

## Architecture

Follows **Clean Architecture / Domain-Driven Design** with a clear separation of layers:

```
packet_tracer_mcp/
+-- adapters/mcp/       -> MCP protocol layer (tools + resources)
+-- application/        -> Use cases + DTOs (input/output)
+-- domain/             -> Pure business logic
|   +-- models/         -> Data models (Plan, Request, Error)
|   +-- services/       -> Services (Orchestrator, IPPlanner, Validator...)
|   +-- rules/          -> Validation rules (devices, cables, IPs)
+-- infrastructure/     -> External concerns
|   +-- catalog/        -> Catalog of devices, cables, templates
|   +-- generator/      -> PTBuilder script + CLI config generators
|   +-- execution/      -> Deployment strategies (manual, live bridge)
|   +-- persistence/    -> Project persistence
+-- shared/             -> Enums, constants, utilities
+-- server.py           -> MCP entry point
+-- settings.py         -> Global configuration
+-- __main__.py         -> Entry point: python -m packet_tracer_mcp
```

## Data flow

```
Request -> TopologyRequest -> Orchestrator -> TopologyPlan -> Validator
                                                v
                                    Generator (PTBuilder JS + CLI configs)
                                                v
                                    Executor (Manual / Deploy / Live Bridge)
```

## Root files

| File | Purpose |
|---------|-----------|
| `server.py` | Creates the `FastMCP` instance, registers tools/resources, starts over HTTP (:39000) or stdio |
| `__main__.py` | Entry point for `python -m packet_tracer_mcp` - invokes `server.main()` |
| `settings.py` | Global constants: `VERSION` (0.4.0), `SERVER_NAME`, `SERVER_INSTRUCTIONS` |

## Execution

```bash
# Streamable HTTP (default, port 39000)
python -m packet_tracer_mcp

# stdio mode (debug/legacy)
python -m packet_tracer_mcp --stdio
```

## Dependencies between layers

```
adapters/mcp -> application/use_cases -> domain/services -> domain/models
                                              v
                                    infrastructure/ (catalog, generator, execution)
                                              v
                                         shared/ (enums, constants, utils)
```

No circular dependencies. The `domain` layer never imports from `infrastructure` directly - communication happens through interfaces.
