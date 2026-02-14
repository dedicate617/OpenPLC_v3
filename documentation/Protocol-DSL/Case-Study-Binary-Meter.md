# Case Study: Binary Meter Read (DSL -> Runtime -> PLC variables)

本案例演示如何把协议文档转换为 DSL，并在 runtime 中完成完整流程。

## 1) 协议条件

- 传输：RS485/RTU, 9600,N,8,1
- 读命令：`68 ADDR 11 04 REG_H REG_L CNT_H CNT_L CRC_L CRC_H`
- 响应：`68 ADDR 91 DATA... CRC_L CRC_H`
- `COUNT=2`，响应携带两个 16-bit 大端值

## 2) DSL 配置

使用：

- `documentation/Protocol-DSL/examples/example-binary-meter-read.json`
- `documentation/Protocol-DSL/protocol-dsl-v0.1.schema.json`

绑定关系：

- `%QW100` -> `ADDR`
- `DATA[0]` -> `%IW100`
- `DATA[1]` -> `%IW101`

## 3) 运行演示

```bash
python documentation/Protocol-DSL/tools/demo_runtime_flow.py
```

### 实际输出（示例）

```text
[TX frame] 68011104000000022405
[RX parsed] {'ADDR': 1, 'DATA': b'\x01,\x00\xfa'}
[PLC image] {'%QW100': 1, '%IW100': 300, '%IW101': 250}
[Alarm state after OK] AlarmState(comm_disconnected=False, comm_error=False, checksum_error=False, last_error_text='')
[RX bad] parse error: CRC mismatch got=0x0000 want=0xBC4E
[Alarm state after bad CRC] AlarmState(comm_disconnected=False, comm_error=True, checksum_error=True, last_error_text='CRC mismatch got=0x0000 want=0xBC4E')
```


### 编译 DSL（Python）再供 C++ 运行时使用

```bash
python webserver/protocol_dsl_compiler.py \
  documentation/Protocol-DSL/examples/example-binary-meter-read.json \
  documentation/Protocol-DSL/examples/example-binary-meter-read.compiled.json
```

该 `*.compiled.json` 可由 C++ runtime 直接加载执行，避免在线解析 DSL 文本带来的运行时开销。

## 4) 结果说明

- TX 报文按模板 + 绑定自动生成。
- RX 正常帧自动解析并写回 PLC 变量 `%IW100/%IW101`。
- CRC 错误帧触发实时 `checksum_error` 和 `comm_error` 告警。

