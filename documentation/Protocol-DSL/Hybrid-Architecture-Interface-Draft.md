# OpenPLC 自由口协议 DSL 混合架构接口草案（Web API + DB + FB）

> 目标：DSL 定义在 Web 侧集中管理，PLC 侧通过 Function Block 进行启停与状态消费。

## 1. 设计范围与原则

### 1.1 范围

本草案定义：

- Web API（会话管理、模板校验、运行控制、状态读取）
- 数据库表（会话主表、字段绑定、告警/统计）
- PLC Function Block 输入输出（控制/状态/数据桥接）

### 1.2 原则

1. **配置与运行解耦**：DSL 配置由 Web/API 管理，PLC 程序只消费运行状态。
2. **兼容现有 Modbus 主站机制**：复用现有 `special_functions` 和后台线程思路。
3. **低抖动优先**：运行时通信线程独立，PLC 主循环仅做短锁拷贝。
4. **可审计可回滚**：所有 DSL 配置具备版本与变更审计。

---

## 2. 架构总览

```text
Web UI/API -> DB(Protocol_Sessions/Bindings/RuntimeState)
            -> Protocol Runtime Engine(Thread)
            -> Shared Runtime State + PLC mirror area
            -> FB: PROTO_SESSION_CTRL / PROTO_SESSION_STATUS
            -> Ladder/ST
```

### 2.1 组件职责

- **Web UI/API**：DSL 编辑、校验、发布、启停、查看统计与告警。
- **Runtime Engine**：按 session 周期组帧/收帧/校验/变量映射。
- **FB 层**：向 PLC 提供控制命令和状态读数，不在 FB 内做模板解析。

---
## 2.2 Python 解析 + C++ 运行时（推荐）

- **Python 负责**：DSL 语法解析、Schema 校验、模板编译（输出 IR JSON）
- **C++ 负责**：高速通信循环（组帧/收帧/校验/统计/告警）

建议编译产物：

- 输入：`session.dsl.json`
- 输出：`session.compiled.json`（包含 `tx_ir` / `rx_ir`）

参考实现文件：

- Python 编译器：`webserver/protocol_dsl_compiler.py`
- C++ 运行时基础：`webserver/core/protocol_dsl_compiled_runtime.h/.cpp`
- 传输层（TCP/RTU）：`webserver/protocol_dsl_transport.py`（`tcp_client` 与 `serial`）

---

## 3. 数据库接口草案

> 推荐新增 4 张表（不影响现有 `Slave_dev` / `Slave_dev_Registers`）。

## 3.1 `Protocol_Sessions`

```sql
CREATE TABLE Protocol_Sessions (
    session_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name     TEXT    NOT NULL UNIQUE,
    version          TEXT    NOT NULL DEFAULT '0.1',
    protocol_kind    TEXT    NOT NULL CHECK(protocol_kind IN ('binary','ascii','mixed')),
    transport_type   TEXT    NOT NULL CHECK(transport_type IN ('serial','tcp_client','tcp_server')),
    transport_json   TEXT    NOT NULL,
    tx_template      TEXT    NOT NULL,
    rx_template      TEXT    NOT NULL,
    match_json       TEXT,
    runtime_json     TEXT,
    enabled          INTEGER NOT NULL DEFAULT 0,
    published_rev    INTEGER NOT NULL DEFAULT 1,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## 3.2 `Protocol_Bindings`

```sql
CREATE TABLE Protocol_Bindings (
    binding_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL,
    field_path       TEXT    NOT NULL,
    direction        TEXT    NOT NULL CHECK(direction IN ('plc_to_proto','proto_to_plc','const')),
    source_ref       TEXT,
    target_ref       TEXT,
    const_value      TEXT,
    cast_type        TEXT,
    scale            REAL,
    offset           REAL,
    clamp_min        REAL,
    clamp_max        REAL,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES Protocol_Sessions(session_id) ON DELETE CASCADE
);
```

## 3.3 `Protocol_Runtime_State`

```sql
CREATE TABLE Protocol_Runtime_State (
    session_id            INTEGER PRIMARY KEY,
    running               INTEGER NOT NULL DEFAULT 0,
    health                TEXT    NOT NULL DEFAULT 'idle',
    last_error_code       INTEGER,
    last_error_text       TEXT,
    last_rtt_ms           INTEGER,
    last_rx_at            DATETIME,
    tx_count              INTEGER NOT NULL DEFAULT 0,
    rx_ok_count           INTEGER NOT NULL DEFAULT 0,
    timeout_count         INTEGER NOT NULL DEFAULT 0,
    checksum_error_count  INTEGER NOT NULL DEFAULT 0,
    comm_error_count      INTEGER NOT NULL DEFAULT 0,
    disconnected_count    INTEGER NOT NULL DEFAULT 0,
    updated_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES Protocol_Sessions(session_id) ON DELETE CASCADE
);
```

## 3.4 `Protocol_Revision_History`

```sql
CREATE TABLE Protocol_Revision_History (
    rev_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    revision          INTEGER NOT NULL,
    payload_json      TEXT    NOT NULL,
    changed_by        TEXT,
    changed_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_note       TEXT,
    FOREIGN KEY(session_id) REFERENCES Protocol_Sessions(session_id) ON DELETE CASCADE
);
```

---

## 4. Web API 草案

> API 前缀建议：`/api/protocol-sessions`

## 4.1 会话 CRUD

### `POST /api/protocol-sessions`

- 功能：创建会话（含模板与传输配置）
- 请求体（示例）

```json
{
  "session_name": "meter_binary_read",
  "version": "0.1",
  "protocol_kind": "binary",
  "transport": {
    "type": "serial",
    "serial": {"port":"/dev/ttyUSB0","baud":9600,"parity":"N","data_bits":8,"stop_bits":1}
  },
  "tx": {"template":"68 {ADDR:u8} 11 04 {REG:u16be} {COUNT:u16be} {CRC16_MODBUS}"},
  "rx": {"template":"68 {ADDR:u8} 91 {DATA:bytes(COUNT*2)} {CRC16_MODBUS}"},
  "match": {"timeout_ms":250,"retry":2,"frame_start":"68","min_len":8,"checksum_required":true},
  "runtime": {"period_ms":100,"on_error":"keep_last"}
}
```

### `GET /api/protocol-sessions/{id}`

- 返回会话详情（含 binding、runtime_state、published_rev）

### `PUT /api/protocol-sessions/{id}`

- 更新会话配置（未发布草稿）

### `DELETE /api/protocol-sessions/{id}`

- 删除会话及 binding/runtime_state/history

## 4.2 绑定管理

### `PUT /api/protocol-sessions/{id}/bindings`

- 一次性覆盖绑定列表

```json
{
  "bindings": [
    {"field":"ADDR","direction":"plc_to_proto","source_ref":"%QW100","cast_type":"u8"},
    {"field":"DATA[0]","direction":"proto_to_plc","target_ref":"%IW100","cast_type":"u16be"},
    {"field":"DATA[1]","direction":"proto_to_plc","target_ref":"%IW101","cast_type":"u16be"}
  ]
}
```

## 4.3 校验与发布

### `POST /api/protocol-sessions/{id}/validate`

- 校验项：
  1. JSON Schema
  2. EBNF 可解析
  3. binding 字段完整性
  4. 表达式可求值性
  5. 变量地址合法性（%IX/%QX/%IW/%QW）

- 响应：

```json
{
  "ok": false,
  "errors": [
    {"code":"E_FIELD_NOT_FOUND","message":"binding field DATA[2] not in rx template"}
  ]
}
```

### `POST /api/protocol-sessions/{id}/publish`

- 将草稿版本写入 `Protocol_Revision_History`
- `published_rev += 1`
- 通知 runtime 进行 reload（不中断策略可配置）

## 4.4 运行控制与监控

### `POST /api/protocol-sessions/{id}/start`
### `POST /api/protocol-sessions/{id}/stop`
### `POST /api/protocol-sessions/{id}/restart`

### `GET /api/protocol-sessions/{id}/status`

```json
{
  "session_id": 1,
  "running": true,
  "health": "ok",
  "last_error_code": 0,
  "last_error_text": "",
  "last_rtt_ms": 18,
  "tx_count": 420,
  "rx_ok_count": 419,
  "timeout_count": 1,
  "checksum_error_count": 0,
  "comm_error_count": 1,
  "disconnected_count": 0
}
```

### `GET /api/protocol-sessions/{id}/trace?limit=200`

- 返回最近报文 trace（默认脱敏）
- 字段：`timestamp, direction, raw_hex, parse_result, checksum_ok`

---

## 5. Runtime 与现有模块接口

## 5.1 Runtime Engine 内部接口（建议）

- `int load_session_config(session_id)`
- `int validate_session_config(session_id)`
- `int start_session(session_id)`
- `int stop_session(session_id)`
- `int build_tx_frame(session_id, uint8_t* out, size_t* out_len)`
- `int parse_rx_frame(session_id, uint8_t* in, size_t in_len)`
- `int sync_plc_mirror(session_id)`

## 5.2 与现有 `special_functions` 映射建议

保留已有 Modbus 统计占位后，新增 DSL 统计槽位（草案）：

- `%ML1034`：DSL active session count
- `%ML1035`：DSL total comm error count
- `%ML1036`：DSL total checksum error count
- `%ML1037`：DSL total timeout count

---

## 6. Function Block 接口草案

> FB 只负责“控制 + 状态读取”，不做 DSL 字符串解析。

## 6.1 `PROTO_SESSION_CTRL`（控制块）

### 输入（IN）

- `EN : BOOL`
- `SESSION_ID : UINT`
- `ENABLE : BOOL`  （使能会话）
- `START : BOOL`   （上升沿启动）
- `STOP : BOOL`    （上升沿停止）
- `RELOAD : BOOL`  （上升沿重载已发布配置）
- `ACK_ALARM : BOOL`（确认并清除可清类告警）

### 输出（OUT）

- `ENO : BOOL`
- `BUSY : BOOL`
- `DONE : BOOL`
- `OK : BOOL`
- `ERR : BOOL`
- `ERR_CODE : DINT`

## 6.2 `PROTO_SESSION_STATUS`（状态块）

### 输入（IN）

- `EN : BOOL`
- `SESSION_ID : UINT`

### 输出（OUT）

- `ENO : BOOL`
- `RUNNING : BOOL`
- `HEALTH : UINT`（0 idle / 1 ok / 2 warn / 3 error）
- `CONNECTED : BOOL`
- `COMM_ERROR : BOOL`
- `CHECKSUM_ERROR : BOOL`
- `TIMEOUT_ERROR : BOOL`
- `LAST_ERR_CODE : DINT`
- `LAST_RTT_MS : UINT`
- `TX_COUNT : UDINT`
- `RX_OK_COUNT : UDINT`
- `COMM_ERROR_COUNT : UDINT`
- `CHECKSUM_ERROR_COUNT : UDINT`
- `TIMEOUT_COUNT : UDINT`

## 6.3 `PROTO_DATA_MAP`（可选数据桥接块）

- 用于将运行时字段值映射到 PLC 中间寄存器区
- 若绑定已直接写 `%IW/%QW`，该块可省略

---

## 7. 端到端调用时序（示例）

1. Web `POST /protocol-sessions` 创建会话
2. Web `PUT /bindings` 配置字段映射
3. Web `POST /validate` 通过
4. Web `POST /publish` 发布并触发 runtime reload
5. PLC 程序调用 `PROTO_SESSION_CTRL(START:=TRUE)`
6. PLC 程序周期读取 `PROTO_SESSION_STATUS`
7. 若 `CHECKSUM_ERROR=TRUE`，PLC 触发工艺报警并可 `ACK_ALARM`

---

## 8. 实际案例（与现有示例对齐）

会话：`meter_binary_read`

- `ADDR <- %QW100`
- `DATA[0] -> %IW100`
- `DATA[1] -> %IW101`

运行结果预期：

- 正常响应：`%IW100=300`, `%IW101=250`
- CRC 错误响应：`CHECKSUM_ERROR=TRUE`, `COMM_ERROR=TRUE`, `LAST_ERR_CODE` 非 0

---

## 9. 方案优先级建议

1. 先实现 Web API + DB + runtime reload（MVP）
2. 再实现 `PROTO_SESSION_CTRL/STATUS` 两个 FB
3. 最后实现 Trace 页面与批量模板导入

