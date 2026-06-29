# astrbot_plugin_twrpg_query

世界RPG（TWRPG）离线查询 AstrBot 插件。

更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 用法

在群聊或私聊中发送（无需 `/` 前缀）：

```
世界 洞悉·真理之瞳
界 太阳石
世界 世界破坏者
世界世界破坏者
英雄 追星剑圣
技能 升龙击
```

插件会以图片卡片展示以下信息（有数据才显示对应区块）：

**物品查询**

- **佩戴限定**：可佩戴英雄头像（与 QuickSearch 一致）
- **专属效果**：英雄头像 + 专属技能改动说明
- **属性**：GamePanel 金色边框 + War3 彩色描述与被动
- **合成方式**：合成所需材料（含图标）
- **可合成物品**：以该物品为材料的合成目标（含图标）
- **来源**：BOSS 掉落（含 BOSS 图标）

**英雄查询**

- 英雄头像、职业名、角色名
- 全部技能：图标 + 热键（如 `[Q]`）+ 描述

**技能查询**

- 技能图标、名称、热键、描述
- 所属英雄（含头像）

## 安装

```bash
cd AstrBot/data/plugins
git clone <本仓库地址> astrbot_plugin_twrpg_query
```

依赖：`Pillow`（安装插件时自动安装）

## 数据

插件自带 `data/twrpg_query/` 离线数据，来源于 `twrpg_data_tools/extracted_data/`。

更新数据时，将以下文件复制到 `data/twrpg_query/`：

- `items.json`
- `makes.json`
- `drops.json`
- `bosses.json`
- `heros.json`
- `exclusives.json`
- `item_passives.json`（被动/主动描述，可用 `scripts/extract_passives.py` 生成）

英雄技能数据可用 `scripts/extract_hero_skills.py` 从 QuickSearch 重新提取并合并至 `heros.json`。

图标与背景资源可通过 `scripts/sync_assets.py` 从本地 QuickSearch 同步到 `assets/icons/` 与 `assets/items_bg.png`。

## 开发调试

1. 将插件放入 `AstrBot/data/plugins/`
2. 启动 AstrBot
3. WebUI → 插件管理 → 重载插件
