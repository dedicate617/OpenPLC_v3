# PR Title

`[mpi] Free-port Protocol-DSL full stack: Python compile + C++ runtime + TCP/RTU + Modbus block/alarm`

## Background

This PR ports the Protocol-DSL/free-port communication solution to `mplc_runtime` branch `mpi` with the same architecture:

- Frontend configures DSL
- Backend Python validates/compiles DSL to compact IR
- Runtime communication executes in C++ (TCP + RTU)
- Modbus register-block and per-device alarms are enabled

## Scope (Phase A~E)

### Phase A
- Baseline and gap alignment to `mpi` code layout

### Phase B
- Python DSL compiler (`protocol_dsl_compiler.py`)
- C++ compiled runtime primitives (`protocol_dsl_compiled_runtime.*`)
- C++ runtime core (`protocol_dsl_runtime.*`)

### Phase C
- Web APIs:
  - `GET /api/protocol-dsl/sessions`
  - `POST /api/protocol-dsl/compile`

### Phase D
- Modbus register-block DB/UI/runtime support
- Device alarm summaries (disconnect / comm / checksum)

### Phase E
- Documentation + examples + demo scripts

## Commit Breakdown

1. `feat(dsl): add python compiler for session templates to tx_ir/rx_ir`
2. `feat(runtime-core): add C++ checksum primitives for compiled protocol runtime`
3. `feat(runtime-core): add C++ free-port runtime cycles for TCP and RTU`
4. `feat(api): add protocol-dsl compile/list endpoints for frontend configuration`
5. `feat(modbus-db): add Slave_dev_Registers table and helpers`
6. `feat(modbus-ui): add register-block config fields in web pages`
7. `feat(modbus-cfg): emit/read block-based mbconfig entries`
8. `feat(modbus-runtime): add multi-block polling and device alarm summary`
9. `docs(dsl): add v0.1 spec/schema/examples and case studies`
10. `test(demo): add tcp+rtu end-to-end demo scripts`

## Validation

- `python -m py_compile webserver/protocol_dsl_compiler.py webserver/protocol_dsl_runtime.py documentation/Protocol-DSL/tools/demo_runtime_flow.py`
- `python documentation/Protocol-DSL/tools/demo_full_chain_tcp_rtu.py`
- `g++ -std=c++11 -fsyntax-only webserver/core/protocol_dsl_compiled_runtime.cpp -Iwebserver/core`
- `g++ -std=c++11 -fsyntax-only webserver/core/protocol_dsl_runtime.cpp -Iwebserver/core`

## Notes

If target repo/network policies block direct cherry-pick from local path, use patch export/import:

```bash
git format-patch -k -1 <commit>
git am 0001-*.patch
```
