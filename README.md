# zyagent

[![CI](https://github.com/wanname777/zyagent/actions/workflows/ci.yml/badge.svg)](https://github.com/wanname777/zyagent/actions/workflows/ci.yml)

`zyagent` 是一个小而完整的 Agent 后端。项目参考视频
[《10 分钟学会设计 Agent 架构》](https://www.bilibili.com/video/BV1winH6DEgt/)
的分层方法，从领域语言开始设计，再由应用层编排流程、适配层连接外部系统。

它不是对某个 Agent 框架的包装，核心代码只依赖 Python 标准库。

## 已实现

- OpenAI 兼容模型协议，可通过 `OPENAI_BASE_URL` 接入兼容服务
- 独立的主模型、工具审核模型和压缩模型配置
- 带最大迭代次数的工具调用循环
- JSONL 会话存储，写入使用临时文件原子替换
- 只读 Bash、工作区文件读取和原子写入工具
- 模型审核加本地确定性校验的双层工具安全
- 会话分支和上下文压缩两项视频作业
- 零第三方运行时依赖，Python 3.9 及以上可用

## 架构

```text
src/zyagent/
├── domain/                 # 系统自己的语言
│   ├── messages.py         # 消息、工具调用、审核结论、摘要
│   ├── session.py          # 会话、分支、摘要边界
│   ├── context.py          # 发给模型的上下文
│   ├── roles.py            # Assistant 与 ToolCallReviewer
│   └── tool.py             # Tool 端口
├── application/
│   ├── ports.py            # ModelClient 与 SessionStore 端口
│   └── service.py          # Agent 循环、分支、压缩
├── adapters/
│   ├── models/openai.py    # OpenAI 兼容协议
│   ├── stores/jsonl.py     # JSONL 持久化
│   └── tools/              # Bash 与文件工具
├── main.py                 # 组装根
└── cli.py                  # 命令行入口
```

依赖方向始终指向领域层。`AgentService` 只认识端口，不依赖 OpenAI 或
JSONL 的具体实现；替换模型和存储时不需要修改 Agent 循环。

## 两项作业

### 1. 分支对话

每条消息都有稳定 ID。`Session.branch(message_id)` 复制指定消息及其之前的
完整历史，生成带 `parent_session_id` 和 `branch_message_id` 的新会话。
父子会话之后分别持久化，互不影响。

如果分支点早于当前摘要边界，新分支会丢弃不再有效的摘要并使用原始历史；
如果分支点在摘要边界之后，则安全继承摘要。

```bash
zyagent show SESSION_ID
zyagent branch SESSION_ID MESSAGE_ID
```

### 2. 对话压缩

压缩不会删除历史消息。它只记录模型生成的摘要及摘要覆盖到的消息 ID，
后续上下文由“摘要 + 最近消息”组成。这样既降低模型费用和延迟，也保留了
审计、展示和从旧消息分支的能力。

```bash
zyagent compress SESSION_ID --keep-recent 12
```

默认组装会在活动上下文达到 24 条消息时自动压缩，并保留最近 12 条。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

配置模型：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export ZYAGENT_MODEL="gpt-4.1-mini"
export ZYAGENT_REVIEWER_MODEL="gpt-4.1-mini"
export ZYAGENT_COMPRESSION_MODEL="gpt-4.1-mini"
```

开始对话：

```bash
zyagent chat
zyagent chat "检查当前工作区并概括项目结构"
zyagent chat --session SESSION_ID "继续刚才的任务"
```

会话默认保存在 `~/.zyagent/sessions.jsonl`。可通过 `--data-path` 修改，
工具工作区默认是当前目录，可通过 `--workspace` 指定。

## 安全边界

- 每个工具调用先交给独立 Reviewer 判断是否符合用户意图。
- Bash 不经过 shell，只执行单条命令。
- Bash 仅允许只读程序和只读 Git 子命令。
- Shell 操作符、命令替换、越界路径和修改型参数会被本地策略拒绝。
- 文件工具解析真实路径，拒绝工作区外路径和通过符号链接越界。
- 命令有超时和输出长度上限。

模型审核不是安全边界，本地确定性校验才是最终执行门。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

测试覆盖 Agent 循环、工具审核、分支语义、增量压缩、模型协议翻译、
JSONL 往返、原子写入和工作区安全约束。
