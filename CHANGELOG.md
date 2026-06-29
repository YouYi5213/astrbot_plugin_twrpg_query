# 更新日志

本文件记录 [世界RPG 查询](https://github.com/YouYi5213/astrbot_plugin_twrpg_query) 插件的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号与 GitHub Release 一致。

---

## [1.0.10] - 2026-06-28

### 新增

- 拦截误用「界」前缀查询三国杀界武将：完全匹配界将名时回复「滚回去玩你的三国杀！」（如 `界 赵云`、`界赵云`）
- 收录界·标、界·风林火山及常见界将名单（见 `sgs_jie_heroes.py`）

---

## [1.0.9] - 2026-06-28

### 修复

- 部分装备在「可合成物品」等区块显示为 `@Old Quest`：同一物品 ID 在数据中存在重复条目（占位任务物覆盖真实装备），加载时现优先保留真实装备名称（如「奥义之核」合成链中的「神煞者印章」）

---

## [1.0.8] - 2026-06-28

### 新增

- 新增 `CHANGELOG.md`，汇总各版本更新说明

### 修复

- 技能标题不再重复显示热键：移除名称中的 `(Q)` 等括号后缀，仅保留 `[Q]` 形式（如「圣光裂空 [Q]」，不再显示「圣光裂空(Q) [ Q ]」）
- 英雄/技能卡片底部内容被裁切：修正高度估算与绘制不一致的问题，并增加底部留白

### 变更

- 支持 `世界 世界破坏者`、`世界世界破坏者` 等写法，自动去掉重复关键字后查询

---

## [1.0.7] - 2026-06-28

### 新增

- **英雄查询**：`英雄 <名>` / `英 <名>`，展示头像、职业名、角色名及全部技能
- **技能查询**：`技能 <名>` / `技 <名>`，展示技能图标、热键、描述及所属英雄
- 从 QuickSearch 离线数据合并 375 条英雄技能至 `heros.json`
- 新增 `scripts/extract_hero_skills.py` 用于技能数据提取

---

## [1.0.6] - 2026-06-28

### 修复

- 佩戴限定区块中部分英雄无图标数据时仍占位，导致头像网格出现空隙（如「世界破坏者」）
- 「世界破坏者」被动描述中的换行乱码

### 变更

- 佩戴限定仅展示有图标数据的英雄，头像连续排列

---

## [1.0.5] - 2026-06-28

### 新增

- 插件 `logo.png`（256×256）

---

## [1.0.4] - 2026-06-28

### 修复

- 合成配方「二选一」材料被拆成多行独立条目的问题
- 可选材料组合并为一行，并以 `[可选]` 标注

---

## [1.0.3] - 2026-06-28

### 新增

- 物品卡片标题右侧显示红色阶段标签（如 `[四大]`、`[大天使]`）

---

## [1.0.2] - 2026-06-28

### 新增

- 佩戴限定改为英雄头像网格展示
- 专属效果独立区块，含英雄头像与技能改动说明

---

## [1.0.1] - 2026-06-28

### 新增

- 物品图标、被动描述与 GamePanel 金色属性框样式
- 内置 NotoSansSC-Bold 字体，修复 Docker / Linux 中文方框

---

## [1.0.0] - 2026-06-28

### 新增

- 世界RPG 离线物品查询插件首次发布
- 支持 `世界 <物品名>` / `界 <物品名>` 图片卡片查询
- 展示属性、合成、掉落、佩戴限定、专属效果等信息

---

[1.0.10]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.10
[1.0.9]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.9
[1.0.8]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.8
[1.0.7]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.7
[1.0.6]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.6
[1.0.5]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.5
[1.0.4]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.4
[1.0.3]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.3
[1.0.2]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.2
[1.0.1]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.1
[1.0.0]: https://github.com/YouYi5213/astrbot_plugin_twrpg_query/releases/tag/v1.0.0
