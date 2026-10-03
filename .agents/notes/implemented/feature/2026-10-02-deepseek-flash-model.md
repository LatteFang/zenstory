# Agent Note: 写作 Agent 模型从 deepseek-v4-flash 升级到 deepseek-flash（DeepSeek-V4.1-Flash）

Status: implemented

## Problem

写作 Agent、路由、`LLMClient`（自然润色等）与素材拆解流程（`flows/utils/clients/llm.py`）都只用一个模型，模型名写死在 `apps/server/agent/core/deepseek_client.py` 的 `DEEPSEEK_CHAT_MODEL`，此前是 `deepseek-v4-flash`。

2026-10-02 实测 DeepSeek `GET /models`：列表里只剩 `deepseek-flash`（DeepSeek-V4.1-Flash，1M 上下文，最大输出 393216，输入支持文本与图片，effort 档位 low/high/max、默认 high）和 `deepseek-v4-pro`。旧名 `deepseek-v4-flash` 仍可调用，但会被静默映射，响应里的 `model` 字段返回 `deepseek-flash`。也就是说我们请求的模型名已经不在官方列表里，日志、SSE 事件里自报的模型名（`deepseek-v4-flash`）和实际服务的模型（`deepseek-flash`）不一致。

## Decision

1. `DEEPSEEK_CHAT_MODEL = "deepseek-flash"`。`LLMClient.MODEL_FAST/MODEL_QUALITY`、`openai_agents/model.py` 的 `DEEPSEEK_WRITING_MODEL`、路由 `_route_with_deepseek_chat`、素材流程 `DeepSeekClient.model` 都引用这个常量，随之切换；runner 发出的 `{"model": ..., "agent_type": ...}` 事件也随之变成 `deepseek-flash`。
2. `LLMClient._resolve_model` 仍只接受这一个模型名：显式传入 `deepseek-v4-flash` 会被拒绝（ValueError），代码里没有调用方这样传。
3. 写作 Agent 与路由不改调用参数：不传 effort（使用模型默认 high），不开图片输入，`max_tokens`、温度等保持原值。2026-10-03 实测 Chat Completions 接受两种推理开关：`reasoning_effort`（none/minimal/low/medium/high/xhigh/ultra/max，未知值返回 422）和 `extra_body={"thinking": {"type": "disabled"}}`。runner 的注释记录这两个已验证字段，并说明写作 Agent 有意保持默认 effort。
4. `LLMClient.acomplete(thinking_enabled=False)` 现在真正关闭推理：请求带 `extra_body={"thinking": {"type": "disabled"}}`；`thinking_enabled=True`（默认）不带任何字段。此前该参数是空操作。传 False 的调用方是输入建议（`agent/suggest_service.py`，`RESPONSE_MAX_TOKENS=150`）和自然润色（`services/features/natural_polish_service.py`）。deepseek-flash 默认推理，reasoning token 计入 `max_tokens`：实测 150 token 的建议调用被推理全部吃光（`finish_reason=length`、正文为空），用户拿到的是兜底文案；关闭推理后约 30–40 token 即返回完整 JSON。真实 LLM 测试 `tests/real_llm/test_agent_suggest_real_llm.py` 断言结果不全是兜底文案。
5. 用量计费不按模型名分档：`writing_stats_service.py` 的单价来自 `AI_USAGE_*_COST_PER_1M_USD` 环境变量，没有以模型 id 为键的价目表，所以不需要改；前端（`apps/web/src`）没有显示或比较模型名。
6. README / README_EN / `docs/docker-compose.md` / `.env*.example` / `agent/CLAUDE.md` 与测试里的模型名一并改为 `deepseek-flash`。

## Alternatives considered

- **保留 `deepseek-v4-flash`，依赖 DeepSeek 的别名映射**。最强理由：零代码改动，实际服务的已经是同一个模型。被否：别名不在官方模型列表里，随时可能被下线，下线时所有 Agent 调用会同时失败；而且我们自报的模型名与响应里的不一致，排查日志时容易误判。
- **把输入建议的 `RESPONSE_MAX_TOKENS` 调到 1024 以上，继续让模型推理**。最强理由：不依赖供应商私有字段，推理可能让建议更贴合上下文。被否：三条十几个字的建议不需要推理，放大预算只是为推理买单，延迟和成本成倍增加；而调用方本来就声明了 `thinking_enabled=False`，把参数接通才是该参数的本意。
- **改用 `deepseek-v4-pro`**。最强理由：能力更强。被否：单价与延迟更高，写作 Agent 一轮会有多次工具调用和路由调用，成本放大明显；本次目标只是跟上模型列表的变化，不是换档位。

## Consequences

- 收益：请求的模型名与官方列表、响应里的 `model` 字段一致；不再依赖可能被移除的别名。
- 收益：输入建议恢复为真实模型输出（此前 deepseek-flash 下绝大多数请求静默回退到兜底文案），润色调用更快、更省 token。
- 代价：自然润色不再推理，润色质量依赖模型的直接输出（抽样实测输出正常）；`thinking` 字段是 DeepSeek 私有参数，若供应商改名，`thinking_enabled=False` 的调用会收到 4xx，需要跟进。
- 代价：任何外部脚本或部署方如果自己按 `deepseek-v4-flash` 过滤日志或 SSE 事件里的模型名，需要改成 `deepseek-flash`。新模型的 effort 档位与图片输入没有利用，默认 effort 为 high，reasoning token 消耗可能与旧模型不同，需要上线后看用量统计；路由的 `max_tokens=2048` 是按旧模型的推理长度留的余量，如果出现路由回退到 writer/quick 的情况要先看这里。
