# PICO-8 技术与开发体系简报

调研基线：2026-07-17；官方手册版本：PICO-8 v0.2.7。版本相关结论在实际项目中应重新核验。

## 目录

1. 平台模型与限制
2. 程序生命周期
3. P8 Lua
4. 图形、地图、音频、输入与存档
5. 内存与性能
6. 工具链与发布
7. 常见代码组织模式
8. 分析时的关键检查项
9. 一手来源

## 1. 平台模型与限制

PICO-8 是一台“幻想游戏机”：规范、编辑器、运行时、卡带、在线浏览器 SPLORE 与社区共同构成平台。限制不是模拟旧硬件的副产品，而是用来推动“小而有表达力”的设计约束。

| 项目 | 官方规格 |
|---|---:|
| 显示 | 128×128，固定 16 色调色板 |
| 控制器 | 每位玩家 6 个按钮；最多 8 个玩家索引 |
| 卡带 | 32 KiB 数据；可编码为 PNG |
| 源码 | P8 Lua；最多 8192 tokens |
| CPU | 约 4M Lua VM 指令/秒；官方也描述为 8 MHz、约 2 cycles/VM instruction |
| 精灵 | 128 个独立 8×8 精灵，另有 128 个与地图共享空间 |
| 地图 | 128×32；使用共享空间时可到 128×64 |
| 音频 | 4 通道；64 个 SFX，每个最多 32 个音符 |

关键限制：

- `.p8.png` / `.p8.rom` 中代码压缩后必须小于 15360 字节，整张卡带不超过 32 KiB；文本 `.p8` 保存时不执行该压缩限制。
- 程序最大 8192 tokens。字符串和成对括号各计一个 token；注释、逗号、句点、`local`、分号和 `end` 等不计入。
- 60 fps 模式每帧只有 30 fps 模式约一半的 CPU 预算。
- 精灵表下半区与地图下半区共享存储；修改一方可能破坏另一方。

## 2. 程序生命周期

常规程序使用四个特殊回调：

- `_init()`：卡带启动后调用一次。
- `_update()`：30 Hz 逻辑更新。
- `_update60()`：替代 `_update()`，请求 60 Hz 更新。
- `_draw()`：每个可见帧调用。

运行时把所有代码标签页从左到右拼接为一个程序后执行。若帧超预算，30 fps 模式可能降到 15 fps，并在一次可见绘制之间执行两次 `_update()`；60 fps 模式也可能降低绘制频率并补做逻辑更新。因此：

- 把模拟放在 update，把渲染放在 draw。
- 不要用 draw 次数驱动游戏时间。
- 在 update 内读取 `btnp()`；其边沿状态会在每次 update 开始时重置。
- 用 `time()` / `t()` 时记住它们由 update 调用次数推导，不是墙上时钟。

项目也可自行写主循环并调用 `flip()`，但多数卡带不需要。

## 3. P8 Lua

P8 Lua 基于 Lua 语法，但没有 Lua 标准库，而是使用 PICO-8 小型 API。重要差异：

- 数字是 16:16 定点数，约为 `-32768` 到 `32767.99999`；每帧递增的长计数器可能在约 18 分钟溢出。
- 三角函数使用一圈 `0..1`，且 `sin()` 为适应屏幕坐标而反向。
- 数组默认从 1 开始；`all()`、`foreach()`、`add()`、`del()`、`deli()` 围绕这种表用法设计。
- 支持短写法：单行 `if (...) statement`、`+=`、`-=`、`..=`、`!=` 等。
- 外部文本编辑器可直接编辑 `.p8`；`#include` 可在启动时注入 `.lua` 或另一卡带的标签页，导出时会被展开。
- P8SCII 包含按钮、图形和日文字符；字节值不能直接当作 UTF-8 解码。

## 4. 图形、地图、音频、输入与存档

### 图形

所有绘图受 draw state 影响：camera、palette remap、clip、当前颜色和 fill pattern。核心 API 包括 `spr/sspr`、`map`、`pset/pget`、`sget/sset`、线框与填充图元。精灵 flag 有 8 位，没有平台预定义语义，常被项目约定为 solid、hazard、foreground、spawn marker 等。

### 地图

地图单元是 8 位值。编辑器默认把它解释为精灵索引，但源码可把它当任意数据。常见用法：

- tilemap + sprite flags 驱动碰撞；
- 地图值作为实体生成标记，关卡开始时转为运行时对象；
- 直接把地图区当压缩数据或查找表；
- 使用共享区换取更大地图，牺牲后 128 个精灵。

### 音频

每个 SFX 有 32 个音符，每个音符包含 pitch、instrument、volume、effect；另有 speed、loop start/end。64 个 music patterns 各引用最多 4 个 SFX 通道。`sfx()` 播放效果，`music()` 播放 pattern 序列。分析时要检查音效是否承担：动作确认、危险预警、命中层级、状态转换、节奏提示，而不只统计数量。

### 输入

`btn()` 读取持续状态，`btnp()` 读取按下边沿/重复。默认玩家 0 为方向键 + O/X，按钮索引 0..5。分析组合输入时要区分键盘与物理手柄的实际可按性，避免仅凭源码推断操作体验。

### 存档

`cartdata(id)` 打开 256 字节永久槽位；`dset/dget` 读写 64 个数。适合最高分、解锁和小型进度。更大数据可用 `cstore/reload`，但会带来版本迁移与卡带交换问题。

## 5. 内存与性能

PICO-8 有三类内存：64 KiB base RAM、32 KiB cart ROM、约 2 MiB Lua RAM。卡带运行时会把 ROM 的 `0x0000..0x42ff` 复制到 base RAM。

| 地址 | 用途 |
|---|---|
| `0x0000` | GFX |
| `0x1000` | GFX2 / MAP2 共享区 |
| `0x2000` | MAP |
| `0x3000` | sprite flags |
| `0x3100` | music patterns |
| `0x3200` | SFX |
| `0x4300` | user data（base RAM）；卡带文件中从这里开始是代码区 |
| `0x5e00` | 256 字节 persistent cart data |
| `0x5f00` | draw state |
| `0x5f40` | hardware state |
| `0x5f80` | GPIO |
| `0x6000` | 8 KiB screen buffer |

用 `stat(1)` 或运行时 CPU meter 检查负载。性能分析优先找：

- 每帧全表嵌套扫描，如 bullets × enemies；
- 大量 `pget/sget/mget` 随机访问；
- 每帧创建大量短命表；
- 无裁剪的大地图/粒子渲染；
- 在 60 fps 模式中执行本可降频的 AI、寻路或生成。

## 6. 工具链与发布

内置编辑器覆盖 code、sprite、map、SFX、music。常用流程：

1. `save foo` / `load foo` 管理 `.p8`；拖放也可加载。
2. `ctrl-r` 重新加载并运行；外部文件改变且编辑器无未保存修改时会自动重载。
3. `info` 查看 code size、tokens、compressed size。
4. `export` 生成 sprite sheet/label PNG、WAV、`.p8.png`、HTML/JS、WASM 或原生二进制。
5. `install_demos` 获取官方示例；`install_games` 获取一小批 BBS 游戏。
6. SPLORE 用于浏览、缓存和运行在线卡带。

官方支持 Windows、macOS、Linux、Raspberry Pi；可导出 HTML5 和桌面二进制。导出与分发仍须取得卡带作者和贡献者许可。

## 7. 常见代码组织模式

以下是样本与社区代码的归纳，不是官方强制规范：

- **回调换绑状态机**：菜单、游戏、结算分别把 `_update/_draw` 指向不同函数。
- **显式状态分派**：保留固定 `_update/_draw`，内部按 `screen/state` 调度。
- **原型对象表**：`type.new()` + `__index`，实体各自 update/draw。
- **组件/系统式对象池**：实体是一组命名组件，system 筛选后批处理。
- **tile flag 碰撞**：把 solid/hazard/one-way 等语义编码在 flag 中。
- **地图即实体清单**：启动关卡时扫描 tile，生成对象并把静态地图与动态实体分开。
- **输入宽容窗口**：jump buffer、coyote time、cooldown 等把有限输入变得更顺手。
- **视觉“juice”层**：screenshake、freeze/hitstop、闪烁、浮字、粒子、短音效与过渡。

## 8. 分析时的关键检查项

- 主回调是否直接定义，还是在 `_init()` 中动态换绑？
- 逻辑运行在 30 Hz 还是 60 Hz？速度常量是否按帧写死？
- 地图/精灵 flag 是否承载碰撞与生成语义？
- 实体列表如何增删？删除时是否可能跳过元素？
- 全局变量哪些是状态，哪些是临时缓存？
- `time()`、帧计数和取模是否影响生成概率或可重现性？
- hitbox、视觉 sprite 与碰撞盒是否分离？
- 失败到重试需要多少帧/按键？是否保存最高分或进度？
- 哪些反馈是规则可读性的必要组成，而非装饰？
- 哪些行为是核心设计规则，哪些只是限制下的实现方式，如全局状态、固定帧速度或 O(n²) 碰撞？

## 9. 一手来源

- PICO-8 官方页：https://www.lexaloffle.com/pico-8.php
- 官方资源页：https://www.lexaloffle.com/pico-8.php?page=resources
- PICO-8 v0.2.7 官方手册：https://www.lexaloffle.com/dl/docs/pico-8_manual.html
- 官方 FAQ：https://www.lexaloffle.com/pico-8.php?page=faq
