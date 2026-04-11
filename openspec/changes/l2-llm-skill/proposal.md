## 为什么

v1 规则引擎在已覆盖场景下准确率高，但对新型/复杂故障模式泛化能力弱。当前实测显示约 20% 的 trace 无法匹配现有规则（confidence < 0.8），这些 case 只能返回 "unknown" 或低置信度结果，严重影响用户信任度和自动化路由效率。

引入 L2 LLM Skill 作为兜底层，可在不牺牲 L1 规则引擎的高效性和可解释性的前提下，用 LLM 推理能力覆盖长尾场景。

## 变更内容

1. **新增 L2 LLM Skill 推理模块**
   - 当 L1 规则引擎 confidence < 0.8 或无匹配规则时，触发 L2 推理
   - 结构化输入：span 树摘要 + 错误链 + L1 初步结果
   - 结构化输出：JSON 格式的 TriageResult
   - Prompt 内嵌四层架构模型 + 三层归因算法约束

2. **新增置信度路由器**
   - 基于 L1 输出的 confidence 和 matched_rules 数量决定是否调用 L2
   - 可配置阈值（默认 0.8）

3. **扩展 TriageResult 结构**
   - 新增 `source: "rules" | "llm"` 字段标识归因来源
   - 新增 `reasoning: str` 字段记录 LLM 推理过程（仅 L2 模式）

4. **新增 API 端点（可选）**
   - `POST /api/trace/analyze-hybrid`：强制启用混合模式
   - 现有端点行为不变（默认启用混合模式）

## 功能 (Capabilities)

### 新增功能
- `llm-skill-inference`: L2 LLM 推理模块，接收结构化 trace 摘要，输出结构化归因结果
- `confidence-router`: 置信度路由器，根据 L1 结果决定是否触发 L2

### 修改功能
- `triage-engine`: 扩展 triage() 函数支持混合模式，返回结果增加 source 和 reasoning 字段

## 影响

- **后端代码**：
  - `triage_engine.py`：扩展 triage() 函数
  - 新增 `llm_skill.py`：LLM 推理模块
  - 新增 `router.py`：置信度路由逻辑
  - `models.py`：扩展 TriageResult 模型

- **API**：
  - `/api/trace/analyze` 返回结构扩展（向后兼容）
  - 可选新增 `/api/trace/analyze-hybrid`

- **依赖**：
  - 新增 `anthropic` SDK（Anthropic API 兼容格式）
  - API Key 由前端本地存储，通过请求头传递

- **配置**：
  - 前端 UI 配置，支持运行时切换 Provider
  - 默认配置（阿里云 DashScope）：
    ```json
    {
      "ANTHROPIC_BASE_URL": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
      "ANTHROPIC_MODEL": "qwen3.6-plus"
    }
    ```

- **前端**：
  - **新增 LLM 配置界面**：
    - API Base URL（支持 DashScope / Anthropic / 其他兼容服务）
    - 模型名称（qwen3.6-plus / claude-sonnet-4-6 等）
    - L2 触发阈值（默认 0.8）
    - API Key（本地 localStorage 存储，不上传服务器）
  - 定界结果面板显示归因来源（规则/LLM）
  - LLM 模式下显示推理过程
