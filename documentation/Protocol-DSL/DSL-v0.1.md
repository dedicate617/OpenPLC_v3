# OpenPLC Free-Port Protocol DSL v0.1 (Draft)

> 目标：让 PLC 开发人员基于设备协议文档，仅通过“发送协议 + 检测协议 + 变量绑定”完成串口/TCP 自由口协议配置。

## 1. Scope

本规范定义：

- 报文模板语法（Binary + ASCII）
- 会话配置模型（transport/match/runtime）
- 字段绑定与 PLC 变量映射
- 校验、长度关联、常量字段与动态字段

不包含：

- UI 交互细节
- 具体运行时线程实现

---

## 2. Top-level JSON Model

```json
{
  "version": "0.1",
  "session_name": "meter_rtu_read",
  "protocol_kind": "binary",
  "transport": { ... },
  "tx": { ... },
  "rx": { ... },
  "match": { ... },
  "bindings": [ ... ],
  "runtime": { ... }
}
```

### Required fields

- `version`
- `session_name`
- `protocol_kind`
- `transport`
- `tx.template`
- `rx.template`
- `bindings`

---

## 3. EBNF Grammar (Template String)

> 模板由 token 序列构成，token 之间由一个或多个空白分隔。

```ebnf
template         = token, { wsp, token } ;

token            = fixed_hex
                 | fixed_ascii
                 | field
                 | calc
                 | delimiter
                 | terminator ;

fixed_hex        = hexbyte ;
hexbyte          = ["0x"], hexdigit, hexdigit ;

fixed_ascii      = "\"", { ascii_char }, "\"" ;

field            = "{", ident, ":", field_type, [",", field_opts], "}" ;

field_type       = numeric_type
                 | float_type
                 | bytes_type
                 | string_type ;

numeric_type     = "u8" | "s8" | "u16be" | "u16le"
                 | "s16be" | "s16le"
                 | "u32be" | "u32le"
                 | "s32be" | "s32le" ;

float_type       = "f32be" | "f32le" ;

bytes_type       = "bytes", "(", expr, ")" ;
string_type      = "string", "(", number, ")" ;

calc             = "{", checksum_type, "}" ;
checksum_type    = "CRC16_MODBUS" | "LRC_ASCII" | "XOR8" | "SUM8" ;

delimiter        = "," | ";" | "|" ;
terminator       = "CR" | "LF" | "CRLF" ;

field_opts       = opt, { ",", opt } ;
opt              = "fmt=", format
                 | "width=", number
                 | "pad=", ("zero" | "space")
                 | "scale=", signed_number
                 | "offset=", signed_number ;

expr             = term, { ("+" | "-"), term } ;
term             = factor, { ("*" | "/"), factor } ;
factor           = number | ident | "len(", ident, ")" | "(", expr, ")" ;

ident            = alpha, { alpha | digit | "_" | "." | "[" | "]" } ;
format           = "%d" | "%u" | "%x" | "%02X" | "%.1f" | "%.2f" | "%.3f" ;

wsp              = " " | "\t" ;
```

---

## 4. Field Semantics

- 固定字节：`68`, `0x68`
- 固定字符串：`"$RD,"`
- 动态字段：`{ADDR:u8}`、`{TEMP:f32le}`
- 变长字段：`{DATA:bytes(LEN*2)}`
- 校验字段：`{CRC16_MODBUS}`
- 结束符：`CR` / `LF` / `CRLF`

### 4.1 `protocol_kind`

- `binary`：默认将 `fixed_hex` 视为单字节
- `ascii`：默认将 `fixed_ascii` 和分隔符用于文本帧
- `mixed`：允许 ASCII 头 + Binary payload 组合

### 4.2 Checksum Rules

- `CRC16_MODBUS`：对帧起始到 CRC 前一字节计算，低字节在前（little-endian）
- `LRC_ASCII`：对 ASCII 负载字节做 LRC
- `XOR8`/`SUM8`：对指定窗口（默认全文）计算

---

## 5. Bindings

`bindings` 是字段与 PLC 变量/常量的桥接配置。

```json
{
  "field": "ADDR",
  "direction": "plc_to_proto",
  "source": "%QW100",
  "cast": "u8"
}
```

### 5.1 Direction

- `plc_to_proto`：组帧时从 PLC 变量取值
- `proto_to_plc`：解帧后写入 PLC 变量
- `const`：固定值，仅用于模板组装

### 5.2 Address format

- 位：`%IXn`, `%QXn`
- 字：`%IWn`, `%QWn`
- 也可预留符号：`symbol:TankLevel`

### 5.3 Optional transforms

- `scale`
- `offset`
- `clamp` (`[min,max]`)

---

## 6. Match block

```json
{
  "timeout_ms": 200,
  "retry": 2,
  "frame_start": "68",
  "min_len": 8,
  "contains": ["91"],
  "checksum_required": true
}
```

规则：

1. `timeout_ms` 内未收齐 -> 通讯超时
2. 命中 `frame_start` 且长度 >= `min_len` 才进入解析
3. `checksum_required=true` 且校验失败 -> 校验告警

---

## 7. Runtime block

```json
{
  "period_ms": 100,
  "max_inflight": 1,
  "on_error": "keep_last",
  "backoff": {
    "mode": "exponential",
    "start_ms": 500,
    "max_ms": 5000
  }
}
```

---

## 8. Validation rules (MUST)

1. `version` 必须为 `0.1`
2. `tx.template` / `rx.template` 必须可被 EBNF 解析
3. `bindings[].field` 必须存在于模板字段集（或 `const`）
4. 变长字段表达式中引用的标识符必须可解析
5. `proto_to_plc` 必须提供 `target`
6. `plc_to_proto` 必须提供 `source`
7. 校验字段只能出现 0 或 1 次（每个模板）

---

## 9. Error/Alarm mapping建议

运行时应至少映射以下状态：

- `comm_disconnected`
- `comm_error`
- `checksum_error`
- `last_error_code`
- `last_error_text`

建议暴露给 PLC 侧作为特殊寄存器或状态 FB 输出。

---

## 10. Compatibility

- v0.1 允许新增字段，但不得改变现有字段语义
- `additionalProperties` 在 Schema 中默认 false（除 `extensions`）


---

## 11. 实际案例演示（端到端）

仓库内提供可直接运行的演示脚本：

- `documentation/Protocol-DSL/tools/demo_runtime_flow.py`

### 运行方式

```bash
python documentation/Protocol-DSL/tools/demo_runtime_flow.py
```

### 预期输出（简化）

1. 输出按 `example-binary-meter-read.json` 组装的 TX 帧（hex）
2. 解析一帧合法 RX，写回 PLC 映射（例如 `%IW100/%IW101`）
3. 注入坏 CRC 的 RX 帧，触发 `checksum_error` + `comm_error`

该示例覆盖：`DSL配置 -> runtime组帧 -> 收帧解析 -> 变量写回 -> 告警状态` 的完整流程。
