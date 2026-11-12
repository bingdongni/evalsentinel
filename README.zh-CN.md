# EvalSentinel

[English](README.md) · 有状态智能体评测器的离线反例测试工具

v0.1 提供 **30 个具名对照**：8 个 MCP 分页对照和 22 个 OWASP 审批/证据边界
对照。直接调用固定版本的原生实现，保留原始判定与异常。无需 GPU 或模型
API key，不运行真实转账、删除等动作。

无需本地安装也可试用：[在自己的 fork 中运行原生演示](docs/try-it.md)，然后
[提交简短试用反馈](https://github.com/bingdongni/evalsentinel/issues/new?template=trial-feedback.yml)。

## v0.3 alpha：MCP 生产检查和执行覆盖门禁

对已启动的本地 MCP 2026-07-28 服务，运行原样的上游 caching CLI，再按明确声明的
生产策略判断适用性。只声明 tools 的服务不会因为缺少 prompts/resources 而误报；
声明了能力却返回错误仍会阻断。原生判定、退出码和检查 ID 完整保留。

```sh
evalsentinel check mcp --checkout /path/to/conformance --expected-commit FULL_40_HEX_SHA --url http://127.0.0.1:8765/mcp --contract production-caching-v1 --output-dir /path/to/new-report
```

**0** 表示有限检查范围通过，**1** 表示范围内违反，**2** 表示不可判定或执行错误。
wire 成功不计入语义覆盖率；全跳过不能变成语义通过。空资源列表保留
`resources/read: not_run`。也可用 `check mcp-report` 为已有原生报告指定必测检查 ID，
无需再跑服务。详见[准备、原生对照和 CI 接入](docs/mcp-production-gate.md)。
这轮复现已公开的 #516，不重复上游已有贡献，也不代表完整 MCP 认证。

## v0.2+：检查自己的 OWASP 评测器提交

OWASP 断言维护者可以指定当前 PR 的完整提交号与单次审批策略，直接接入 CI：

```sh
evalsentinel check owasp --checkout /path/to/harness --expected-commit FULL_40_HEX_SHA --contract single-use-approval-v1 --output-dir /path/to/new-report
```

退出码 **0** 表示 18 个语义对照与两个可执行守卫符合声明策略；**1** 表示契约违反；
**2** 表示运行、原生接口或源码身份校验失败。两个证据不支持的性质单独列出。
调用者可检查兼容的当前或未来提交，原有历史版本复现实验仍可使用。
详见[安装与维护者 CI 接入说明](docs/maintainer-gate.md)。外部维护者采用情况仍未验证。

## 已验证的正反对照

对 OWASP 原版及其已有修复 PR #211 使用相同的 22 例：

| 结果 | 原版 | 待合并修复版 |
| --- | ---: | ---: |
| 单次审批策略下的误通过输入 | 6 | 0 |
| 正常输入正确接受 | 7 | 7 |
| 错误行为正确拒绝 | 5 | 11 |
| 未执行敏感动作 | 1 | 1 |
| 原生证据不足以支持的性质 | 2 | 2 |
| 故意输入错误 | 1 | 1 |

这是对已公开问题和策略差异的验证，不是发现了六个新漏洞。原版明确采用了
较弱的 MVP 授权策略；修复仍是上游未合并的 PR。时序与终态证据不足时不猜测，
未执行、未支持和异常不算成功检出。

## 快速运行（Python + Git，无需 Node）

安装 Python 3.12+、Git 和 uv 后：

```sh
git clone https://github.com/bingdongni/evalsentinel.git
cd evalsentinel
uv sync --locked --no-dev
uv run --no-dev python tools/prepare_native.py --adapter owasp
uv run --offline --no-dev evalsentinel audit owasp --checkout .cache/owasp-fixed --revision candidate --require-sound --output-dir runs/fixed
```

将 checkout 换为 `.cache/owasp-harness`、revision 换为 `baseline`，严格门禁会
以退出码 1 拒绝已知误通过；修复版退出 0。每次使用新的输出目录。

准备依赖和源码需要网络；实验不调用模型 API。完整 30 例矩阵需要 Node 22，
命令见英文 README。完整矩阵为 60 行观测，不能把两个协议版本或两个修订版
的重复运行算成新的独立案例。

## 参与

欢迎提交可复现的 issue、补充有来源的回归用例，或从
[good first issue](https://github.com/bingdongni/evalsentinel/labels/good%20first%20issue)
开始。请阅读 [贡献指南](CONTRIBUTING.md)，保留正常与异常对照、原生结果和
证据能力边界。若工具对你的工作有帮助，也欢迎 star，让更多维护者找到它。

实现和验证使用了 Codex 辅助；详细方法、限制和上游归属见英文 README。
