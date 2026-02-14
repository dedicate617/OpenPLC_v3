# Migration Playbook: OpenPLC_v3 -> mplc_runtime (branch: `mpi`)

目标：在目标仓库 `https://github.com/dedicate617/mplc_runtime` 的 `mpi` 分支上，按 PhaseA~E 生成**单一功能提交**，并最终推送到新分支 `mb_free_protocol`。

> 说明：当前环境无法直连 GitHub（403），本文件提供可在可联网环境直接执行的迁移步骤与 commit 切分。

---

## Phase A — 仓库基线与差异评估

```bash
git clone https://github.com/dedicate617/mplc_runtime.git
cd mplc_runtime
git checkout mpi
git checkout -b mb_free_protocol
```

### A1. 建立差异清单（建议）

- 对照 OpenPLC_v3 的以下能力模块：
  1) DSL 编译器（Python）
  2) C++ Runtime（TCP/RTU）
  3) Web API（compile/list sessions）
  4) Modbus register-block + alarms

**建议提交（单一功能）**

- `chore(migration): add phase-A gap analysis for protocol DSL + modbus blocks`

---

## Phase B — 核心能力迁移（编译器与C++运行时）

## B1. Python DSL 编译器

迁移文件：
- `webserver/protocol_dsl_compiler.py`

建议提交：

- `feat(dsl): add python compiler for session templates to tx_ir/rx_ir`

## B2. C++ compiled runtime primitives

迁移文件：
- `webserver/core/protocol_dsl_compiled_runtime.h`
- `webserver/core/protocol_dsl_compiled_runtime.cpp`

建议提交：

- `feat(runtime-core): add C++ checksum primitives for compiled protocol runtime`

## B3. C++ runtime 主循环接口（TCP + RTU）

迁移文件：
- `webserver/core/protocol_dsl_runtime.h`
- `webserver/core/protocol_dsl_runtime.cpp`

建议提交：

- `feat(runtime-core): add C++ free-port runtime cycles for TCP and RTU`

---

## Phase C — Web/API 与前端配置闭环

迁移文件：
- `webserver/webserver.py`（新增 `/api/protocol-dsl/compile` 与 `/api/protocol-dsl/sessions`）
- （可选）前端页面入口与调用逻辑

建议提交：

- `feat(api): add protocol-dsl compile/list endpoints for frontend configuration`

---

## Phase D — Modbus register-block 与告警增强

迁移文件：
- `webserver/check_openplc_db.py`
- `webserver/pages.py`
- `webserver/webserver.py`
- `webserver/core/modbus_master.cpp`
- `webserver/core/utils.cpp`

建议提交拆分：

1. `feat(modbus-db): add Slave_dev_Registers table and helpers`
2. `feat(modbus-ui): add register-block config fields in web pages`
3. `feat(modbus-cfg): emit/read block-based mbconfig entries`
4. `feat(modbus-runtime): add multi-block polling and device alarm summary`

---

## Phase E — 文档、样例与验收脚本

迁移文件：
- `documentation/Protocol-DSL/*`
- `documentation/Protocol-DSL/tools/demo_runtime_flow.py`
- `documentation/Protocol-DSL/tools/demo_full_chain_tcp_rtu.py`

建议提交拆分：

1. `docs(dsl): add v0.1 spec, schema and examples`
2. `docs(case-study): add TCP/RTU full-chain walkthrough`
3. `test(demo): add demo scripts for tcp+rtu end-to-end validation`

---

## 建议的最终提交序列（示例）

1. chore(migration): phase-A gap analysis
2. feat(dsl): python compiler
3. feat(runtime-core): checksum primitives
4. feat(runtime-core): C++ TCP/RTU runtime cycle
5. feat(api): frontend compile/list APIs
6. feat(modbus-db): register-block table
7. feat(modbus-ui): register-block form fields
8. feat(modbus-cfg): block-based mbconfig generation
9. feat(modbus-runtime): multi-block + alarms
10. docs(dsl): spec/schema/examples
11. docs(case-study): TCP/RTU walkthrough
12. test(demo): runtime demos

---

## 一键执行模板（在 mplc_runtime 仓库内）

```bash
# 0) branch
git checkout mpi
git checkout -b mb_free_protocol

# 1) 按 Phase A~E 逐步迁移文件并每步 commit
# (此处按上方建议提交顺序逐个 add/commit)

# 2) 自检（按可用性调整）
python -m py_compile webserver/protocol_dsl_compiler.py webserver/protocol_dsl_runtime.py documentation/Protocol-DSL/tools/demo_runtime_flow.py
python documentation/Protocol-DSL/tools/demo_full_chain_tcp_rtu.py || true
g++ -std=c++11 -fsyntax-only webserver/core/protocol_dsl_compiled_runtime.cpp -Iwebserver/core

# 3) 推送
git push -u origin mb_free_protocol
```

---

## PR 描述建议（摘要）

- 采用 Python 编译 DSL + C++ 执行通讯线程，降低运行时解析开销
- 同步支持 TCP 与 RTU 自由口全链路
- 增强 Modbus 多块与告警可观测性
- 前端可直接配置 DSL 并触发编译

