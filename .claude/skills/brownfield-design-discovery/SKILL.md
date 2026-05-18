---
name: brownfield-design-discovery
description: |
  在使用 OpenSpec 生成设计文档之前，强制完成「现有实现盘点 + 公共 SDK 能力覆盖矩阵 + 复用/自实现决策」三件套，避免 OpenSpec 凭用户口述生成脱离现状或忽视可复用 SDK 的设计，从而避免重复造轮子和实施返工。

  立即触发的场景（遇到以下任意一种就要使用此 skill，不要绕开）：
  - 用户说「在现有 X 基础上扩充 / 扩展 / 增强」、「基于现有能力做增量」、「不要重新造轮子」
  - 用户说「优先使用公司 / 团队 / 集团的 SDK」、「先用 SDK，SDK 不满足再自实现」、「SDK first」
  - 用户提到「加 QoS / 加流控 / 加限流 / 加配额 / 加熔断 / 加重试 / 加日志埋点」等明显有公共 SDK 候选的横切能力
  - 用户准备运行 /opsx:propose 或 /opsx:explore，但目标 feature 在仓库里已有相关代码（brownfield）
  - 用户抱怨「OpenSpec / CodeAgent 生成的设计没看代码」「忽略了 SDK」「在重新造轮子」「设计和现状对不上」
  - 任何同时满足「扩展已有 capability」+「有公共 SDK 候选」两个约束的场景

  即使用户只提到其中一个方面（例如「只盘点一下 SDK 能力」），也应跑完两条分析线并产出决策矩阵——单边分析必然导致「已有能力被忽视」或「SDK 假装能用其实有缺口」。

  本 skill **不**用于：纯 greenfield 项目（无任何相关现有代码、无候选 SDK）；纯 bug 修复或局部重构；与现有能力扩展无关的全新横向功能。
---

# Brownfield Design Discovery

在 OpenSpec 生成 `design.md` 之前强制完成「现有实现 + SDK 覆盖 + 复用决策」三件套，再把产物喂回 `openspec-propose`。

## 核心理念

**代码是真相，SDK 文档是契约，设计不能脱离两者**。OpenSpec / 内部 CodeAgent 在 brownfield 场景默认会有两个失败模式：

1. **不读代码** → 设计与现状不兼容：重复造已有抽象、错过现有扩展点、与现有调用方接口冲突。
2. **不读 SDK** → 要么把 SDK 已经能做的事自实现一遍（维护成本翻倍），要么把 SDK 做不到的事当成「应该能做」（实施时返工）。

**核心约束**：**任何「自实现」决策都必须显式回答两个问题**：

- 现有代码里没有可复用 / 可扩展的实现吗？引用文件 + 行号。
- 公共 SDK 真的不支持吗？引用 SDK 文档章节 + 版本号。

回答不上来的一律打回 Step 2 / Step 3，**不要靠「快速决策」绕过盘点**。

## 工作流（五步）

每一步显式产出文件，缺一步就在最终交付里标注「未做」，不要静默跳过。

### Step 1 — 范围与前置确认

在动数据之前先确认（用户没给齐就用 **AskUserQuestion** 主动问）：

1. **变更名称**：kebab-case（例如 `add-qos-rate-limit`、`extend-flow-control-with-quota`）。还没有 OpenSpec change 也要先定名，Step 5 启动 propose 时复用。
2. **新需求描述**：1–3 句话讲清「要做什么」+「为什么现在做」。
3. **现有实现入口**：要扩展 / 复用的现有模块路径（例如 `src/middleware/ratelimit/`、`pkg/flowcontrol/`）。用户不知道就先用 Grep/Glob 在仓库里找候选并和用户确认。
4. **公共 SDK 信息**：
   - 包名 + 版本（例如 `com.company.qos-sdk:2.3.0`）
   - 文档 / 示例位置（README、API 文档、内部 wiki 链接、源码路径）
   - **拿不到任何一项就停下来要**，不要凭 SDK 名字猜能力。
5. **决策偏好**：团队是否允许「小范围自实现」，或必须 SDK + SDK 扩展点优先？

把答案写进 `openspec/changes/<change-name>/discovery/scope.md`。这一步不写下来，后面所有断言都没有立足点。

### Step 2 — 现有实现盘点

对照新需求扫描现有代码。至少回答下表所有维度（缺哪栏说明扫描不到位，回去补 Grep）：

| 维度 | 说明 | 取证方式 |
|---|---|---|
| 入口 / API 表面 | 现有能力对外暴露的接口（函数 / 类 / 注解 / 配置） | Grep + Read 关键文件 |
| 内部数据模型 | 配置、规则、状态的存储结构 | Read 模型定义 |
| 扩展点 | hook、策略接口、SPI、配置驱动开关 | Grep `interface` / `abstract` / `Strategy` / `Provider` |
| 调用链 | 谁调用现有能力（消费方分布） | Grep 调用点 |
| 已知限制 | 现有实现做不了的事（这正是新需求的动机） | 用户访谈 + 代码注释 + issue |
| 测试覆盖 | 哪些行为已有测试托底 | Glob test 文件 |

输出 `openspec/changes/<change-name>/discovery/existing-capability-inventory.md`，模板：

```markdown
# 现有实现盘点

## 范围
- 扫描路径: <paths>
- 扫描日期: <YYYY-MM-DD>

## API 表面
| 接口 | 文件:行 | 用途 | 调用方数量 |
|---|---|---|---|
| <name> | `src/...py:42` | <desc> | N |

## 扩展点
| 扩展点 | 类型 | 位置 | 是否适合新需求 |
|---|---|---|---|
| <name> | hook / strategy / SPI | `src/...:88` | 是 / 否 / 部分 |

## 已知限制（驱动新需求的痛点）
- L1: <description> — 见 `src/...:120`
- L2: ...

## 测试覆盖
- 现有行为测试: `tests/...`
- 缺口: <未覆盖的关键路径>

## 给设计的输入
- 推荐复用: <list>
- 推荐扩展（而非重写）: <list>
- 不可复用、需要新建: <list>（每一项后续要 SDK 覆盖矩阵验证）
```

**强制规则**：如果「扩展点」一栏全空，要么扫描不彻底（回去再 Grep 一遍 `interface` / `abstract` / `Strategy` / `Provider` / `SPI`），要么现有实现确实无扩展点——必须明确写「无扩展点，新能力只能并行新建模块」。不允许留空。

### Step 3 — 公共 SDK 能力覆盖矩阵

把新需求拆成原子能力点（atomic capabilities），逐点在 SDK 中找证据。

输出 `openspec/changes/<change-name>/discovery/sdk-coverage-matrix.md`，模板：

```markdown
# SDK 能力覆盖矩阵

## SDK 信息
- 包名 / 版本: `<group:artifact:version>`
- 文档来源: <link or path>
- 评估日期: <YYYY-MM-DD>

## 原子能力拆解 + 覆盖判断

| # | 原子能力 | 覆盖度 | 证据 (文档章节 / API) | 缺口 / 备注 |
|---|---|---|---|---|
| 1 | 令牌桶限流 | 完全 | `RateLimiter.acquire()` 见 docs §3.2 | — |
| 2 | 多维度配额 | 部分（配置） | `QuotaPolicy` 仅支持 2 维 | 业务要 3 维，需要扩展 |
| 3 | 动态热更新 | 部分（扩展点） | 有 `ConfigListener` SPI | 需写 listener 适配 |
| 4 | 用户级熔断 | 不支持 | 文档全文搜索 "user / per-user / per-account circuit" 无命中 | 需自实现或换 SDK |

## 覆盖度等级定义
- **完全**：开箱即用，仅配置即可。
- **部分（配置）**：SDK 支持，但需要非默认配置组合 / 多 API 串联。
- **部分（扩展点）**：SDK 提供 SPI / hook，需要写适配代码。
- **不支持**：SDK 范围外，需要绕开或自实现。

## SDK 版本风险
- 当前版本: ...
- 下一稳定版本预告: ...（是否会补齐缺口？查 release note / roadmap）
- 升级成本估计: ...
```

**强制规则**：
1. 「覆盖度=完全」必须给出具体 API 名 + 文档章节，**不能只写「SDK 应该支持」**。
2. 「不支持」必须做过文档关键字搜索 + sample 代码检查，并在备注里写明**搜过的关键词**，避免漏看。
3. SDK 文档不可获得（拿不到 / 没权限 / 找不到）→ **立刻停下报告用户**，不要凭直觉填表。

### Step 4 — 复用 vs 自实现决策

把 Step 2、3 的结果合成单一决策表。

输出 `openspec/changes/<change-name>/discovery/build-vs-reuse-decision.md`，模板：

```markdown
# 复用 / SDK / 自实现 决策表

| # | 原子能力 | 决策 | 依据 (inventory / matrix 行号) | 风险 |
|---|---|---|---|---|
| 1 | 令牌桶限流 | 用 SDK | matrix #1 完全覆盖；inventory 无此能力 | SDK 版本锁定 |
| 2 | 多维度配额 | SDK + 自实现 wrapper | matrix #2 部分；wrapper 在 SDK 之上聚合 | wrapper 维护成本 |
| 3 | 动态热更新 | 扩展 SDK SPI | matrix #3 + inventory 扩展点「ConfigBus」可对接 | 适配层薄但需测 |
| 4 | 用户级熔断 | 自实现 | matrix #4 不支持；inventory 无类似；业务必须 | 自实现成本最高 |

## 决策护栏复核
对每行 `决策 = 自实现` 或 `SDK + 自实现 wrapper`，**逐条**确认：
- [ ] 现有代码无可复用 / 可扩展实现（引用 inventory 表第 N 行）
- [ ] SDK 当前版本不支持（引用 matrix 表第 N 行）
- [ ] SDK 下一版本短期不会补齐（询问 SDK owner / 查 release note）
- [ ] 自实现范围最小化（不顺手「重写一遍现有能力」）

任何一条不通过就回 Step 2 / Step 3 补全证据，**不要降低标准放行**。

## 给 OpenSpec design.md 的三段输入
1. **现状与扩展点**：摘自 inventory「API 表面 / 扩展点」+ 推荐复用 / 扩展项。
2. **SDK 覆盖与权衡**：摘自 matrix 全表 + 版本风险段落。
3. **复用 / 自实现范围**：本表 + 护栏复核结论。
```

### Step 5 — 喂给 OpenSpec

discovery/ 目录就绪后，进入 OpenSpec。三种情况：

**情况 A — 还没有 change**：
1. 建议用户运行 `/opsx:propose <change-name>` 或直接 `Skill openspec-propose`。
2. 调用 openspec-propose 时**显式**告诉它读取 `openspec/changes/<change-name>/discovery/*.md` 作为 design.md 输入。
3. design.md **必须包含**三个章节，对应 Step 4「三段输入」：
   - 「现状与扩展点」← existing-capability-inventory.md 摘要
   - 「SDK 覆盖与权衡」← sdk-coverage-matrix.md 摘要
   - 「复用 / 自实现范围」← build-vs-reuse-decision.md 摘要
4. proposal.md 的 「Why」 章节**必须引用** inventory.md 的「已知限制」（不是凭空写动机）。

**情况 B — change 已存在但 design.md 还没写好**：
1. 把 discovery/ 三份 md 放到 change 目录下。
2. 让 openspec-propose 重新生成 design 产出物。
3. 同样要求三个章节齐全。

**情况 C — design.md 已写但缺这些章节**：
1. **不要**静默改 design.md。先把 discovery/ 产出展示给用户。
2. 由用户决定增补还是重写。

最后输出汇报模板：

```
## Discovery 完成

- 范围: openspec/changes/<name>/discovery/scope.md
- 现有盘点: existing-capability-inventory.md  ← N 个扩展点 / M 项已知限制
- SDK 矩阵: sdk-coverage-matrix.md            ← X 完全 / Y 部分 / Z 不支持
- 决策:    build-vs-reuse-decision.md         ← 复用 A / SDK B / 扩展 C / 自实现 D

下一步: 调用 openspec-propose <name>
（design.md 三个章节将基于 discovery/ 强制对齐；任何「自实现」都已通过护栏复核）
```

## 关键原则与红线

1. **代码盘点不可跳过**：哪怕用户口头说「现状就是 X」，也要 Grep/Read 验证。口述与代码不一致是 brownfield 最常见的设计陷阱。
2. **SDK 文档不可获得 = 立刻停**：不要靠「SDK 名字像应该支持」的直觉填覆盖矩阵。停下来找文档或问 SDK owner。
3. **「自实现」是默认拒绝选项**：默认优先级 **复用 > SDK 直接用 > SDK 扩展 > 自实现**。每多一阶要多一份证据。
4. **不要把「重复造轮子」包装成「灵活性」**：「自己写一份比 SDK 灵活」是误区，灵活性的真实成本是长期维护和踩坑。
5. **决策表必须可审计**：每行决策都要可追溯到 inventory / matrix 的具体行，review 时能逐条对账。
6. **discovery/ 是只增不改的证据**：评估迭代用 v2/ 追加，不要覆盖 v1；月度复评时旧版本归档。
7. **写「为什么」而不只是「是什么」**：每个决策都要给出可解释的因果（为什么 SDK 不够、为什么扩展点不合适），说不清楚的写「**待 SDK owner 确认**」+ 具体问题，不要为了「完整」硬编。

## 输入 / 输出契约

**输入（最小集）**：
- 新需求 1–3 句话描述（必填）
- 现有实现入口路径或模块名（必填，可由 skill 协助定位）
- 公共 SDK 包名 + 文档位置（必填，拿不到立刻停）
- 变更名 kebab-case（必填或在 Step 1 协助生成）

**输出（必产物）**：

```
openspec/changes/<change-name>/discovery/
├── scope.md
├── existing-capability-inventory.md
├── sdk-coverage-matrix.md
└── build-vs-reuse-decision.md
```

附质量自查清单（写在 scope.md 末尾）：扫描路径覆盖度、SDK 文档来源可信度、决策表护栏复核通过率。

## 与其他 skill 的边界

- 设计文档生成本身 → `openspec-propose`（discovery 完成后调用，把 discovery/ 作为输入）
- 探索性思考 / 问题边界确认 → `openspec-explore`（可在 Step 1 之前先跑，澄清需求再进 discovery）
- 实施任务 → `openspec-apply-change`（design.md 定稿后）
- 多 SDK 之间选哪一个 → `tech-evaluation`（如果连「用哪个 SDK」都没定，先跑选型；本 skill 假设候选 SDK 已确定）
- 商业价值 / 立项评估 → `business-insight`（本 skill 假设需求已立项，不评估业务价值）
- 单条 trace 故障归因、画像分析 → 与本 skill 无关

## 何时跳过本 skill

- **纯 greenfield**：仓库里完全没有相关现有代码、领域也没有候选 SDK → 直接 `openspec-propose`。
- **无候选 SDK，但有现有实现**：仍然要做 Step 2（现有盘点），跳过 Step 3，决策表里 SDK 列填「无候选」。
- **纯 bug 修复 / 局部重构**：不涉及能力扩展 → 直接 `openspec-propose` 或 `openspec-apply-change`。
- **POC / 一次性脚本**：不进入长期维护 → 跳过本 skill，但在 proposal.md 标注「POC，未做 brownfield discovery」。
