---
title: "MCP Gateway 完全指南：Agent MCP Gateway 按需发现工具"
date: 2026-07-02T10:00:00+08:00
slug: "mcp-gateway"
url: "/mcp-gateway.html"
categories:
  - "AI 工程"
tags:
  - "MCP"
  - "Gateway"
  - "Agent"
  - "Cursor"
  - "Claude"
draft: false
---
> 基于开源项目 [roddutra/agent-mcp-gateway](https://github.com/roddutra/agent-mcp-gateway)（当前 **M1-Core Complete**）。下文配置格式与工具说明以官方 README 为准。

## MCP Gateway 完全指南

### 一、MCP Gateway 解决了什么问题？

当你只接入 1-2 个 MCP Server 时，事情很简单——在 Claude Desktop 或 Cursor 的配置文件里把它们列出来就行。

但当 Server 数量从 2 个变成 10 个、20 个，问题就来了。

**第一个问题是“上下文爆炸”。** 在 Claude Code、Cursor 这类开发环境中，所有 MCP Server 的工具定义会在启动时**一次性全部加载**到每个 Agent 和子 Agent 的上下文窗口里。结果是：

- 5,000 到 50,000+ Token 在启动时就被消耗掉
- 80% 到 95% 的工具，Agent 在本次会话中根本用不上
- 真正用于“干活”的上下文空间，被大量无用的工具定义挤占

**第二个问题是配置碎片化。** 每新增一个 MCP Server，就要改一次客户端配置；若不走网关，往往还要重启 IDE 或 MCP 进程。Server 数量从个位数增长到两位数时，配置管理本身就是负担。

**第三个问题是安全和治理缺失。** 每个 MCP Server 各自维护自己的认证授权逻辑，很难做统一的审计、监控和权限管控。

MCP Gateway 就是为了解决这三个问题而生的——它充当 Agent 和多个 MCP Server 之间的代理层，提供统一入口、按需发现工具、策略控制和安全治理。

### 二、方案选型：Agent MCP Gateway

本文聚焦于 **Agent MCP Gateway**——一个开源、轻量、适合中小企业的解决方案。

它的核心设计思路是：**启动时只向 Agent 暴露 3 个网关工具（官方估算约 2k Token）**；需要某 Server 的能力时，再调用 `get_server_tools` 按需拉取工具 schema，用 `execute_tool` 代理执行。相比把全部下游 tool 定义一次性塞进上下文，可显著降低启动占用（官方场景下常见 **90%+** 的节省，具体取决于下游 Server 数量与 schema 大小）。

> 注意：按需发现**不是零成本**——`get_server_tools` 返回的 schema 仍会进入后续对话上下文，只是从「启动全量加载」变成「用时再加载」。

### 三、工作原理

```
┌─────────────────────────────────────────────────────────────┐
│            Agent (Claude Code / Cursor / 其他)              │
│                          │                                  │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │  Agent MCP Gateway   │  ← 单一 MCP 入口      │
│              │  (3 个工具, ~2k Token)│  ← 按需发现          │
│              └───────────┬───────────┘                      │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         ▼                ▼                ▼                │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐             │
│   │PostgreSQL│   │  GitHub  │   │  Slack   │             │
│   │  MCP     │   │  MCP     │   │  MCP     │             │
│   └──────────┘   └──────────┘   └──────────┘             │
└─────────────────────────────────────────────────────────────┘
```

网关默认暴露 **3 个**工具（开启 `GATEWAY_DEBUG=true` 时额外暴露第 4 个诊断工具 `get_gateway_status`）：

| 工具 | 作用 |
| :--- | :--- |
| `list_servers` | 列出当前 Agent 有权限访问的 MCP Server |
| `get_server_tools` | 获取指定 Server 的工具定义（可按策略过滤，支持 `names` / `pattern` / `max_schema_tokens`） |
| `execute_tool` | 在指定 Server 上代理执行工具 |

推荐工作流：**`list_servers` → `get_server_tools` → `execute_tool`**。每次调用建议带上 `agent_id`（或在网关侧配置 `GATEWAY_DEFAULT_AGENT`），以便策略与审计生效。

### 四、安装与配置

#### 第一步：初始化

```bash
uvx agent-mcp-gateway --init
```

会在 `~/.config/agent-mcp-gateway/` 生成模板：

- `.mcp.json` — 下游 MCP Server 定义
- `.mcp-gateway-rules.json` — 按 Agent 的访问策略

（也支持当前目录下的 `.mcp.json` / `.mcp-gateway-rules.json`，或通过环境变量 `GATEWAY_MCP_CONFIG`、`GATEWAY_RULES` 指定路径。）

#### 第二步：配置下游 MCP Server（`.mcp.json`）

使用 **标准 MCP 配置格式**，顶层键为 `mcpServers`（不是 `servers`）：

```json
{
  "mcpServers": {
    "postgres": {
      "description": "PostgreSQL 只读查询",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://..."],
      "env": {}
    },
    "github": {
      "description": "GitHub API",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

也支持 `url` + `transport: "http"` 连接远程 MCP Server。建议为每个 Server 写 `description`，便于 Agent 在 `list_servers` 时理解用途。

#### 第三步：配置访问策略（`.mcp-gateway-rules.json`）

策略文件结构是 **`agents` 对象**（按 agent 名分组），不是 `agents` 数组；deny 写在各 agent 的 `deny` 块里，也没有顶层的 `deny_rules` 数组：

```json
{
  "agents": {
    "coding_agent": {
      "allow": {
        "servers": ["postgres", "github"],
        "tools": {
          "postgres": ["query", "list_tables", "list_schemas"],
          "github": ["create_issue", "list_repos"]
        }
      },
      "deny": {
        "tools": {
          "postgres": ["drop_*", "delete_*"]
        }
      }
    },
    "ops_agent": {
      "allow": {
        "servers": ["postgres", "slack"],
        "tools": {
          "slack": ["send_message"]
        }
      }
    },
    "default": {
      "deny": {
        "servers": ["*"]
      }
    }
  },
  "defaults": {
    "deny_on_missing_agent": false
  }
}
```

规则采用 **Deny-Before-Allow**：显式 deny > 通配 deny > 显式 allow > 通配 allow > 隐式 grant（仅 allow 了 server、未写 tools 时允许该 server 全部工具）> 默认拒绝。

工具名按 **Server 分组**（如 `"postgres": ["query"]`），不是 `postgres__query` 这种扁平命名。

#### 第四步：启动网关

```bash
uvx agent-mcp-gateway
```

默认以 **stdio** 传输运行，供本地 MCP 客户端通过子进程拉起——不是 HTTP 地址。

#### 第五步：配置你的 Agent

客户端里只需注册 **一个** MCP Server 条目，指向网关进程。例如 Claude Code：

```bash
claude mcp add agent-mcp-gateway uvx agent-mcp-gateway
```

或手动配置（路径可按需省略，使用默认 `~/.config/agent-mcp-gateway/`）：

```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "uvx",
      "args": ["agent-mcp-gateway"],
      "env": {
        "GATEWAY_MCP_CONFIG": "~/.config/agent-mcp-gateway/.mcp.json",
        "GATEWAY_RULES": "~/.config/agent-mcp-gateway/.mcp-gateway-rules.json",
        "GATEWAY_DEFAULT_AGENT": "coding_agent"
      }
    }
  }
}
```

在 Agent 的 system prompt（如 `CLAUDE.md`）中说明：调用网关工具时要传 `agent_id`，并遵循 `list_servers` → `get_server_tools` → `execute_tool` 流程。详见[官方 Configure Your Agents 章节](https://github.com/roddutra/agent-mcp-gateway#3-configure-your-agents)。

### 五、核心特性

| 特性 | 说明 |
| :--- | :--- |
| **按需工具发现** | 启动只加载 3 个网关工具；下游 schema 用时再通过 `get_server_tools` 拉取 |
| **Per-Agent 访问控制** | 不同 Agent 可配置不同的 server / tool 权限 |
| **Deny-Before-Allow 策略** | 显式拒绝优先于允许 |
| **通配符支持** | 如 `get_*`、`*_user`、`drop_*` |
| **会话隔离** | 并发请求互不干扰 |
| **透明代理** | 下游 Server 无需感知网关协议细节 |
| **审计日志** | 操作可记录便于追溯 |
| **性能指标** | 延迟、错误率等 |
| **热加载配置** | 修改 `.mcp.json` 或 rules 后无需重启网关 |
| **OAuth 支持** | 下游 HTTP 401 时可走 OAuth 流程（M1） |
| **诊断工具** | `get_gateway_status` 仅在 `GATEWAY_DEBUG=true` 时暴露 |

### 六、与同类方案的对比

MCP Gateway 生态中还有其他方案，各有侧重（以下为定位概括，具体以各项目文档为准）：

| 方案 | 定位 | 差异 |
| :--- | :--- | :--- |
| **Agent MCP Gateway** | 策略驱动的按需发现 | 默认 3 个网关工具，强调 Per-Agent 策略 |
| **@eznix/mcp-gateway** | 服务器聚合 | 暴露更多网关侧工具，统一调用面 |
| **mcp-simple-gateway** | 轻量代理 | 偏 Token 认证，功能较基础 |
| **mcp-foxxy-bridge** | 一对多代理 | 侧重请求路由与聚合 |
| **MCP Gateway（mcpgateway.com）** | 商业/平台化网关 | 提供 SEARCH_TOOLS / EXECUTE_TOOL 等 meta-tool 模式 |

Agent MCP Gateway 的差异化在于：**开源、stdio 友好、策略引擎 + 热加载**，启动上下文占用小（约 2k Token 量级）。

### 七、适用场景与限制

**适用场景**：

- 团队规模 10-50 人
- MCP Server 数量 5-20 个
- 需要统一的访问控制和审计
- 希望快速落地、运维简单

**当前版本状态**（官方 Roadmap）：

- ✅ **M0: Foundation** — 配置、策略引擎、审计日志、`list_servers`
- ✅ **M1: Core** — 代理、`get_server_tools`、`execute_tool`、中间件、指标、热加载、OAuth
- 🚧 **M2: Production** — HTTP Transport、健康检查（计划中）
- 🚧 **M3: DX** — Single-agent 模式、配置验证 CLI、Docker（计划中）

当前版本为 **M1-Core Complete**。

### 八、总结

Agent MCP Gateway 的核心思想可以概括为一句话：**把「工具发现」和「工具执行」拆开，让 Agent 先通过少量网关工具按需拉 schema，再代理执行。**

对于中小企业来说，这套方案的价值在于：

1. **节省启动上下文**：下游 tool 定义不再在会话开始时全部加载
2. **统一管理**：Server 与策略集中在 `.mcp.json` / rules 中，支持热加载
3. **安全可控**：Per-Agent 权限 + Deny-Before-Allow + 审计
4. **快速落地**：`uvx agent-mcp-gateway --init` 即可生成模板配置

**参考**：[roddutra/agent-mcp-gateway](https://github.com/roddutra/agent-mcp-gateway)
