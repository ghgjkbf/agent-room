# GitHub 发布交接文档（TRAE 执行）

日期：2026-08-29 · 交接人：ZCode · 目标：TRAE 独立完成 agent-room 仓库的 GitHub 发布

## 一、当前状态（发布前置已全部就绪）

- 仓库：`d:\ai-use\projects\agent-room`，分支 `main`，HEAD=`ea5bcf4`，tag `v0.6.0`（已打）
- 工作区干净（`git status` 无未提交内容），**无 remote**（未关联任何远端）
- 发布版 README / LICENSE(MIT) / docs（CHANGELOG、设计文档、各步交接）已就位
- **密钥安全已扫描**：全 git 历史 0 泄露；运行时文件（`backend/agent_room.db`、`server.log`、`backend/workspace/`、`backend/data/`、`.venv`、`node_modules`、`src-tauri/target`）均在 .gitignore，**不会也不应随仓库发布**
- 本机无 gh CLI；git 凭据走你（TRAE）侧已配置的方式（credential manager / token）

## 二、发布步骤

1. **向用户确认两件事**（不要自行拍板）：
   - 仓库名（建议 `agent-room`）与可见性（public / private）
   - `docs/STEP*-HANDOFF.md` 三份交接文档是否随仓库公开——内含用户本机成员 id 与运行时状态（无令牌明文），用户同意则保留，否则发布前删除并单独提交
2. **创建远端**（二选一）：
   - 你侧有 GitHub 凭据：`git remote add origin https://github.com/<用户名>/agent-room.git`
   - 或引导用户在 GitHub 网页建空仓库（**不要**勾选初始化 README/license），再执行上一条
3. **推送**：
   ```bash
   git push -u origin main --tags
   ```
4. **发布后验证**（缺一不可）：
   - 网页打开仓库：README 渲染正常（表格/代码块）、LICENSE 存在、tag `v0.6.0` 在 Releases/Tags 里
   - 仓库文件列表**不含**：`agent_room.db`、`server.log`、`.venv`、`node_modules`、`src-tauri/target`、`backend/workspace/`、`backend/data/`
   - `git ls-files` 复核跟踪文件数约 60 个，与本地一致

## 三、红线（执行中绝对禁止）

- **禁止** `git add -f` 任何被 ignore 的文件（尤其 `agent_room.db`——内含令牌哈希与用户 LLM 配置）
- **禁止** 把 `.zcode` 配置、ROOM_TOKEN、API Key 写进任何入库文件或提交信息
- **禁止** force push、改写历史（历史已扫描无密钥，保持原样）
- 推送遇到凭据问题不要重试轰炸，回报用户处理

## 四、验收标准

> push 成功后，任意浏览器（无本地缓存）打开仓库页：README 完整渲染、文件树干净（无运行时文件）、tag v0.6.0 可见——即发布完成。

## 五、完成后

- 向用户回执：仓库 URL、可见性、推送的分支与 tag、文件数
- 可选建议转告用户：仓库 Settings → Topics 加 `mcp` `multi-agent` `fastapi` `tauri` `wechat-style`；About 栏填一句简介（可抄 README 首段）
