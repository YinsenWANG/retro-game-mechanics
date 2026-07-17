# PICO-8 Cartridge 文件结构

## 目录

1. 格式概览
2. `.p8` 文本卡带
3. `.p8.png` 图片卡带
4. 32 KiB 卡带布局
5. 解析流程
6. 工具用法
7. 已知边界
8. 来源

## 1. 格式概览

PICO-8 常见卡带格式：

- `.p8`：可读文本，适合版本控制和外部编辑。
- `.p8.png`：160×205 RGBA PNG；图片低位中编码 32 KiB 卡带和 32 字节 trailer。
- `.p8.rom`：原始 32 KiB 卡带数据。
- `@clip`：剪贴板表示；本 Skill 不直接处理。

官方手册公开了保存、加载、32 KiB 限制和运行时内存布局；`.p8.png` 的低位编码与压缩细节由兼容工具实现和社区格式文档交叉验证。把后者标记为“兼容实现观察”，不要冒充官方稳定 API。

## 2. `.p8` 文本卡带

典型骨架：

```text
pico-8 cartridge // http://www.pico-8.com
version 42
__lua__
-- source
__gfx__
...
__gff__
...
__map__
...
__sfx__
...
__music__
...
__label__
...
```

段可以缺省；末尾全零行通常省略。

| 段 | 逻辑内容 | 文本编码 |
|---|---|---|
| `__lua__` | P8 Lua 源码 | Unicode/P8SCII 可读文本；代码 tabs 已串联 |
| `__gfx__` | 128×128 4bpp sprite sheet | 每行最多 128 个十六进制 nibble；一字符一像素 |
| `__gff__` | 256 个 sprite flag bytes | 每行 256 个 hex 字符，最多两行 |
| `__map__` | 128×64 tile bytes | 每行 256 个 hex 字符，最多 64 行；共享区与 GFX2 重叠 |
| `__sfx__` | 64 个 SFX | 每行 168 字符：8 字符控制信息 + 32×5 字符 note 数据 |
| `__music__` | 64 个 music patterns | 通常为 flag + 4 个 SFX 引用；每行约 11 字符（含分隔空格） |
| `__label__` | 128×128 卡带标签 | 与 GFX 类似的 4bpp 逻辑像素 |

解析时不要假定所有行都存在；缺失部分视为零/空。

## 3. `.p8.png` 图片卡带

兼容实现观察：官方 `.p8.png` 是 160×205、8-bit、non-interlaced RGBA PNG。总像素数 `160×205 = 32800`，恰好容纳：

- `0x8000`（32768）字节卡带；
- `0x20`（32）字节 trailer。

每个像素的 RGBA 四通道各贡献最低 2 位，重建一个 payload byte：

```text
byte = (B & 3)
     | ((G & 3) << 2)
     | ((R & 3) << 4)
     | ((A & 3) << 6)
```

视觉上的卡带标签使用通道高 6 位，因此低位数据不会明显破坏图像。禁止重新压缩为会改变像素值的有损格式。

trailer 的兼容工具实现包含版本、平台标记和 SHA-1 等字段；剩余字节可能保留。分析通常只需保留原始 trailer，不应依赖未公开字段做游戏逻辑推断。

## 4. 32 KiB 卡带布局

| 偏移 | 长度 | 内容 |
|---:|---:|---|
| `0x0000` | `0x2000` | GFX（含与 MAP2 共享的后半） |
| `0x2000` | `0x1000` | MAP |
| `0x3000` | `0x0100` | sprite flags |
| `0x3100` | `0x0100` | music patterns |
| `0x3200` | `0x1100` | SFX |
| `0x4300` | `0x3d00` | 代码区 |

代码区可能是：

- 未压缩、NUL 结尾的 P8SCII；
- 旧格式，头为 `:c:\0`；
- 新格式，头为 `\0pxa`，使用 bit stream、move-to-front 与 LZ back-reference。

解压后仍须按 P8SCII 字节表映射到 Unicode；直接 UTF-8 解码会破坏按钮图标和扩展字符。

## 5. 解析流程

1. 识别输入是文本、PNG 还是原始 ROM。
2. 对 PNG：验证尺寸与色彩格式，恢复所有 scanline filter，再提取低位 payload。
3. 切出 ROM、代码区和 trailer。
4. 按 header 解压代码并转换 P8SCII。
5. 对文本 `.p8`：按 section marker 分段，缺失段补空。
6. 生成结构摘要：callbacks、函数、API 使用、table/global 候选、资源密度。
7. 只在授权允许且任务需要时导出完整源码；默认报告函数名和结构，不复制代码正文。
8. 将静态观察与运行时/游玩观察分开。词法调用图不是运行时 trace。

## 6. 工具用法

本 Skill 的脚本只处理本地文件，不访问 BBS：

```bash
python3 scripts/pico8_cart.py game.p8.png --json
python3 scripts/pico8_cart.py game.p8.png --extract-code game.lua --extract-rom game.rom
python3 scripts/pico8_cart.py game.p8.png --extract-dir unpacked-cart
python3 scripts/analyze_cart.py game.p8.png --format markdown --output static-analysis.md
python3 scripts/create_analysis_case.py game.p8.png case-dir \
  --title "Game" --author "Author" \
  --source-url "https://..." --license "CC BY-NC-SA 4.0" \
  --permission-basis "BBS page explicitly marks this revision CC4-BY-NC-SA"
```

`create_analysis_case.py` 默认不复制卡带，只记录本地文件名和 SHA-256。仅当存储/再分发确有授权时使用 `--copy-cart`。

## 7. 已知边界

- `pico8_cart.py` 的 PNG reader 只接受标准 160×205、8-bit、non-interlaced RGBA 卡带图。
- 静态分析不执行 P8 Lua，无法确认动态函数生成、元表分派、自修改内存或随机行为。
- 函数调用图按相邻函数定义切块，是近似值；内嵌函数与同名方法可能被合并或误归属。
- `.p8` section 数量和行数可被省略；不要用固定行数拒绝合法卡带。
- token 精确计数需要完整 P8 Lua tokenizer；本工具只报告字符、行、函数和 API profile。
- 卡带格式可能随 PICO-8 更新而变；对新版本先用官方 PICO-8 做一次 load/save 对照。

## 8. 来源

- 官方手册（保存、限制、内存布局）：https://www.lexaloffle.com/dl/docs/pico-8_manual.html
- PICO-8 Wiki `.p8` 格式说明：https://pico8wiki.com/index.php?title=P8FileFormat
- PICO-8 Wiki `.p8.png` 格式说明：https://pico8wiki.com/index.php?title=P8PNGFileFormat
- Shrinko8（MIT，兼容格式实现，用于交叉验证）：https://github.com/thisismypassport/shrinko8
