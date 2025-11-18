# Docs Overview

[English Version](README.en.md)

| 文件 | 说明 |
| --- | --- |
| `user_manual.md` / `user_manual.en.md` | 用户部署 & 指令手册（中 / 英）。 |
| `development_guide.md` / `development_guide.en.md` | 接口契约与测试策略（中 / 英）。 |
| `developer_overview.md` / `developer_overview.en.md` | 架构、数据流、扩展注意事项（中 / 英）。 |
| `telegram_architecture.md` / `telegram_architecture.en.md` | Telegram 长轮询、历史拼接、主动策略（中 / 英）。 |
| `user_profile_doc*.md` | 用户画像（敏感信息，Git 已忽略，按需本地维护）。 |

### 建议阅读路径
1. 想了解整体模块 & 运行方式：先读 `developer_overview.md`，再按需查看 `telegram_architecture.md`。
2. 要实现新功能：结合 `development_guide.md` 中的接口签名，以及 `tests/` 里的用例。
3. 使用/部署：查看 `README.md` 与 `docs/user_manual.md`。

### 编辑约定
- 更新文档时同步修改本 README 中的表格，保持“**该文件负责什么**”可见。
- 涉及隐私（`config/settings*.toml`, `user_profile_doc*.md`, `databases/`）的文件不应提交，必要时在 `.gitignore` 中维护忽略项。
