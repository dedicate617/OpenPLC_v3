# Case Study: 自由口通讯全链路（TCP + RTU）

本案例演示同一套 DSL 配置如何完成两种自由口链路：

- TCP Client 自由口
- RTU（串口）自由口

## 1) 关键实现位置

- DSL 编译（Python）：`webserver/protocol_dsl_compiler.py`
- 运行时执行（C++）：`webserver/core/protocol_dsl_runtime.h/.cpp`
- 传输层（TCP + Serial）：`webserver/protocol_dsl_transport.py`
- C++ 高性能原语：`webserver/core/protocol_dsl_compiled_runtime.cpp`

## 2) 前端配置 DSL（Web API）

前端可直接调用后端 API 保存并编译 DSL：

```bash
curl -X POST http://127.0.0.1:8080/api/protocol-dsl/compile \
  -H "Content-Type: application/json" \
  -d @documentation/Protocol-DSL/examples/example-binary-meter-read.json
```

返回 `compiled_file` 后，C++ 通讯线程直接读取该编译结果执行。

可列出已保存会话：

```bash
curl http://127.0.0.1:8080/api/protocol-dsl/sessions
```

## 3) 一键演示脚本

```bash
python documentation/Protocol-DSL/tools/demo_full_chain_tcp_rtu.py
```

该脚本会：

1. 启动本地 TCP 模拟从站
2. 启动 PTY 模拟 RTU 串口从站
3. 用同一 DSL session 分别跑 TCP 与 RTU `run_cycle()`
4. 输出 TX/RX 帧、PLC 映射值与告警状态

## 4) 预期结果

- TCP 路径：能收到有效响应并写回 `%IW100/%IW101`
- RTU 路径：能通过 pseudo-tty 完整走通收发
- 两路径 `AlarmState` 在正常响应时应为无错误

## 5) 说明

当前 demo 用模拟从站验证全链路，适合开发联调与回归。
现场接入时只需替换 transport 参数（IP/Port 或 Serial 端口）。
