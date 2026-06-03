# tests/

Test suite with pytest. 38 tests covering all layers of the domain.

## Execution

```bash
# All tests
python -m pytest tests/ -v

# A specific file
python -m pytest tests/test_full_build.py -v

# A specific test
python -m pytest tests/test_full_build.py::TestFullBuild::test_basic_2_routers -v
```

## Files

| File | Tests | Coverage |
|---------|-------|-----------|
| `test_full_build.py` | 7 | **Integration**: 2 routers, 3 routers+WAN, OSPF, single router, without DHCP, with servers, estimation fields |
| `test_validator.py` | 4 | Validation: valid plan, duplicate name, invalid model, invalid interface |
| `test_generators.py` | 4 | PTBuilder: `addDevice` format, `addLink` format. CLI: hostname config, DHCP pool |
| `test_auto_fixer.py` | 2 | Auto-correction: fix cable type (router-router->cross), no-fix-needed |
| `test_explainer.py` | 3 | Explanations: basic includes routers, DHCP explained, WAN explained |
| `test_ip_planner.py` | 6 | IP: LAN /24 subnets, sequential, inter-router /30, /30 hosts, gateway .1 |
| `test_estimator.py` | 4 | Estimation: basic, WAN adds cloud, simple complexity, complexity scales |
| `test_regressions_runtime.py` | 8 | Regressions: templates, ManualExecutor metadata, multi-hop routes, first IP .2, fix_plan, estimator with laptops/AP, static/DHCP PC config |

## Total: 38 tests, ~400 lines of code
