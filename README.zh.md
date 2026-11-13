# repo2draw

[English](README.md) | 中文

零 AI 依赖的 README 架构图自动同步工具：纯静态分析（正则 + 目录规则）提取仓库的
模块与依赖，拼出 `x-cmd draw` 图表 URL，并自动保持在 `README.md` 占位符之间持续更新。
不调用任何大模型，不在仓库里提交 PNG/SVG——图就是一段 URL。

## 普通用户快速上手

**1. 在你的 README 里加入占位符**（跳过则自动追加到文末）:

```markdown
<!-- ARCH_DIAGRAM_START -->
![Project Architecture](https://x-cmd.com/draw/arch2?title=repo2draw&t=shadcn&n=scripts%3Bsvc%3Bscripts%3B%3Br0c0)
<!-- ARCH_DIAGRAM_END -->
```

**2. 在你的仓库创建 `.github/workflows/arch-diagram.yml`:**

```yaml
name: architecture-diagram
on:
  workflow_dispatch:            # 手动触发
  push:
    branches: [main, master]    # 改成你的默认分支
    paths:                      # 按你的源码路径调整
      - "src/**"
      - "**.py"
      - "**.js"
      - "**.ts"
      - "**.go"

permissions:
  contents: write

concurrency:
  group: repo2draw
  cancel-in-progress: true

jobs:
  sync:
    runs-on: ubuntu-latest
    if: ${{ !contains(github.event.head_commit.message, '[skip ci]') }}
    steps:
      - uses: actions/checkout@v4
      - uses: qiakai/repo2draw@main
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if git diff --quiet -- README.md README.zh.md 2>/dev/null; then
            echo "README unchanged"; exit 0
          fi
          git add README.md README.zh.md 2>/dev/null || git add README.md
          git commit -m "docs: sync architecture diagram [skip ci]"
          git push
```

**3. Push。** 首次运行就会把架构图写入占位符之间；之后每次 push 源码变更
都会自动刷新。

核心就是 `- uses: qiakai/repo2draw@main` 这一步：它会自动拉取分析脚本、
分析已 checkout 的仓库并同步你的 README。上面的 `paths` / `[skip ci]` /
bot 作者校验用来防 push 回写死循环。其他语言请按本仓库
`.github/workflows/sync-arch.yml` 里的扩展名清单补充 `paths`。

## 工作原理（本仓库）

三步流水线，每步一个独立脚本，中间产物可检查、可复用：

1. **`scripts/analyze_arch.py`** — 按特征文件检测主语言，忽略 `.git`、
   `node_modules`、`dist`、`docs`、`examples` 等噪声目录，用正则解析
   import / require / include 提取模块间依赖（节点数封顶 15 个，超出按
   引用度截断；循环依赖通过 SCC 缩点布局）。无法识别语言时优雅降级为
   目录树结构图。**输出 `arch.json` 架构数据**（节点含 id / 类型 / 标签 /
   副标签 / 顶层目录分组 / 网格坐标）。
2. **`scripts/build_diagram.py`** — **根据 `arch.json` 生成图**：把数据编码进
   `https://x-cmd.com/draw/arch2` 的 URL 参数（节点 / 连线 / 分组边界 / 主题），
   输出 Markdown 图片行。长度守卫：>4000 字符告警，>7500 字符拒绝输出。
3. **`scripts/update_readme.py`** — 只做同步：整行锚定正则替换占位符之间的
   内容，无占位符时追加到文末；原子写入、保留文件权限与 CRLF 行尾，
   可同时同步多份 README。

`.github/workflows/sync-arch.yml` 是本仓库自用的流水线（直接运行脚本）,
`action.yml` 就是上文普通用户使用的 Action 入口。

## 支持的语言

| 语言 | 检测特征 | 依赖提取方式 |
| --- | --- | --- |
| Python | `pyproject.toml` / `requirements.txt` / `setup.py` | `import` / `from X import Y`（含相对导入） |
| Node.js | `package.json` | `require` / `import … from`（含相对路径、`@/` 别名） |
| Go | `go.mod` | `import` 块 + module 前缀剥离（根包聚合成单节点） |
| Rust | `Cargo.toml` | `use crate::` / `mod` |
| Java / Kotlin | `pom.xml` / `build.gradle(.kts)` | `import`（包目录递归展开） |
| C# | `*.csproj` / `*.sln` | `using` |
| PHP | `composer.json` | `use`（PSR-4 命名空间）/ `require` |
| Ruby | `Gemfile` | `require` / `require_relative` |
| Swift | `Package.swift` | `import`（Sources 下的 Target） |
| C / C++ | `CMakeLists.txt` / `meson.build` | `#include "…"`（相对路径解析） |
| 其他 / 未知 | 无 | 目录树兜底（虚线边，保证任何仓库都能出图） |

## 配色模型（为什么不单调）

arch2 的节点颜色**由类型固定映射**（无节点级颜色覆盖，已实测确认）:

| 类型 | 图例 | 命中关键词举例 |
| --- | --- | --- |
| `fe` | Frontend | web、ui、pages、templates、views、render |
| `be` | Backend | api、server、routes、controllers、blueprints、services |
| `db` | Database | db、models、storage、cache、repository、dao |
| `cloud` | Cloud | deploy、infra、k8s、docker、metrics |
| `sec` | Security | auth、crypto、oauth、jwt、rbac |
| `bus` | Message bus | queue、events、workers、tasks、signals、hooks |
| `svc` | Service | 默认（未命中任何关键词） |
| `ext` | External | sdk、connector、plugins、compat、client |

在此之上，**分组边界**（`b=` 参数，按顶层目录自动成组，≥2 节点才绘制）拥有独立的
强调色（s8~s10），进一步丰富色板。节点类型由目录/模块名确定性映射，图例始终诚实。

## 效果示例（真实知名仓库，一键生成）

**flask** (Python) — 15 个核心模块（blueprints=Backend、signals=Message bus、
templating=Frontend）,src 分组边界，40 条依赖边经 SCC 缩点分层：

![flask architecture](https://x-cmd.com/draw/arch2?title=flask&t=shadcn&n=app%3Bsvc%3Bapp%3Bentry%3Br1c0&n=blueprints%3Bbe%3Bblueprints%3B%3Br1c1&n=cli%3Bsvc%3Bcli%3Bentry%3Br1c2&n=ctx%3Bsvc%3Bctx%3B%3Br1c3&n=debughelpers%3Bsvc%3Bdebughelpers%3B%3Br2c0&n=globals%3Bsvc%3Bglobals%3B%3Br2c1&n=helpers%3Bsvc%3Bhelpers%3B%3Br2c2&n=sansio%3Bsvc%3Bsansio%3B%3Br0c0&n=sessions%3Bsvc%3Bsessions%3B%3Br2c3&n=signals%3Bbus%3Bsignals%3B%3Br3c0&n=templating%3Bfe%3Btemplating%3B%3Br3c1&n=testing%3Bsvc%3Btesting%3B%3Br3c2&n=typing%3Bsvc%3Btyping%3B%3Br3c3&n=wrappers%3Bsvc%3Bwrappers%3B%3Br4c0&n=tests%3Bsvc%3Btests%3B%3Br0c1&e=app%3Bctx&e=app%3Bdebughelpers&e=app%3Bglobals&e=app%3Bhelpers&e=app%3Bsessions&e=app%3Bsignals&e=app%3Btemplating&e=app%3Btesting&e=app%3Btyping&e=app%3Bwrappers&e=blueprints%3Bcli&e=blueprints%3Bglobals&e=blueprints%3Bhelpers&e=blueprints%3Btyping&e=blueprints%3Bwrappers&e=cli%3Bapp&e=cli%3Bglobals&e=cli%3Bhelpers&e=cli%3Btyping&e=ctx%3Bapp&e=ctx%3Bglobals&e=ctx%3Bhelpers&e=ctx%3Bsessions&e=ctx%3Bsignals&e=ctx%3Btyping&e=ctx%3Bwrappers&e=debughelpers%3Bblueprints&e=debughelpers%3Bglobals&e=debughelpers%3Btyping&e=debughelpers%3Bwrappers&e=globals%3Bapp&e=globals%3Bctx&e=globals%3Bsessions&e=globals%3Btyping&e=globals%3Bwrappers&e=helpers%3Bglobals&e=helpers%3Bsignals&e=helpers%3Btyping&e=helpers%3Bwrappers&e=sansio%3Bctx&b=src%3Bapp%20blueprints%20cli%20ctx%20debughelpers%20globals%20helpers%20sansio%20sessions%20signals%20templating%20testing%20typing%20wrappers)

**gin** (Go) — render=Frontend,internal 工具包分组边界：

![gin architecture](https://x-cmd.com/draw/arch2?title=gin&t=shadcn&n=binding%3Bsvc%3Bbinding%3B%3Br0c0&n=json%3Bsvc%3Bjson%3B%3Br2c2&n=gins%3Bsvc%3BginS%3B%3Br0c1&n=bytesconv%3Bsvc%3Bbytesconv%3B%3Br2c0&n=fs%3Bsvc%3Bfs%3B%3Br2c1&n=render%3Bfe%3Brender%3B%3Br1c0&e=binding%3Bbytesconv&e=binding%3Bjson&e=binding%3Brender&e=render%3Bbytesconv&e=render%3Bfs&e=render%3Bjson&b=internal%3Bbytesconv%20fs)

**express** (Node.js) — view=Frontend,lib 核心分组边界：

![express architecture](https://x-cmd.com/draw/arch2?title=express&t=shadcn&n=index%3Bsvc%3Bindex%3Bentry%3Br0c0&n=application%3Bsvc%3Bapplication%3B%3Br1c0&n=express%3Bsvc%3Bexpress%3B%3Br1c1&n=request%3Bsvc%3Brequest%3B%3Br2c0&n=response%3Bsvc%3Bresponse%3B%3Br2c1&n=utils%3Bsvc%3Butils%3B%3Br3c0&n=view%3Bfe%3Bview%3B%3Br2c2&n=test%3Bsvc%3Btest%3B%3Br0c1&e=application%3Bexpress&e=application%3Butils&e=application%3Bview&e=express%3Bapplication&e=express%3Brequest&e=express%3Bresponse&e=index%3Bexpress&e=response%3Butils&e=test%3Butils&e=test%3Bview&b=lib%3Bapplication%20express%20request%20response%20utils%20view)

## 本地使用（开发本仓库）

```sh
make arch     # 分析 -> 生成图 -> 同步 README.md 与 README.zh.md
make verify   # 重新生成并 HTTP 校验两份 README 中所有内嵌图表 URL
make clean    # 删除中间产物 arch.json / diagram.md
```

没有 `make` 的环境直接用底层命令（与 CI 完全一致）：

```sh
python3 scripts/analyze_arch.py --root . --out arch.json
python3 scripts/build_diagram.py arch.json --out diagram.md
python3 scripts/update_readme.py --image-file diagram.md --readme README.md --readme README.zh.md
```

## 配置

`scripts/build_diagram.py` 顶部的**配置区**可改：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ENDPOINT` | `https://x-cmd.com/draw/arch2` | 渲染端点 |
| `THEME` | `shadcn` | 主题（共 21 种：`xcmd`/`evil`/`pipeline`/`gradient`…） |
| `SCHEME` | `""` | 置为 `dark` 强制暗色 |
| `BOUNDARIES` | `True` | 是否绘制顶层目录分组边界（`--no-boundaries` 可关） |
| `IMG_ALT` | `Project Architecture` | 图片 alt 文本 |

`scripts/update_readme.py` 配置区：`MARK_START` / `MARK_END` 占位符（需独占一行）。

`analyze_arch.py` 参数：`--max-nodes 15`（节点上限）、`--max-edges 40`、
`--max-depth 2`（目录树兜底深度）、`--title`（图标题）。

## 本仓库架构图（自举生成）

<!-- ARCH_DIAGRAM_START -->
![Project Architecture](https://x-cmd.com/draw/arch2?title=repo2draw&t=shadcn&n=scripts%3Bsvc%3Bscripts%3B%3Br0c0)
<!-- ARCH_DIAGRAM_END -->

## 格式说明（x-cmd draw arch2 URL）

```
/draw/arch2?title=<标题>&t=<主题>
    &n=<id>;<类型>;<标签>;<副标签>;<网格>     网格 = r<行>c<列>[w<宽>][h<高>]
    &e=<from>;<to>[;<标签>][;<变体>]        变体 = main|dash（省略为普通箭头）
    &b=<组名>;<id>[ <id>...]               分组边界，id 用空格分隔（≥2 节点才成组）
节点类型：ext fe be db cloud sec bus svc；分号在字段内需编码为 %3B。
```

## 约束与设计取舍

- 只用 Python 3 标准库，CI 运行 < 10s；无任何第三方依赖，零 AI 调用。
- URL 长度守卫：>4000 字符告警，>7500 字符拒绝输出（防止网关截断）。
- 包目录与其子模块同时存在时，子模块提升为节点、父目录折叠，保证图可读。
- 相对导入（`from . import x`）与第三方包不产生边，避免蜘蛛网。
- 不想用 `uses:` 引用？把三个脚本拷贝进你的仓库，再复制
  `.github/workflows/sync-arch.yml` 即可自托管。
