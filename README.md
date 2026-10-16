# Sig · 签名工作台

**中文** | [English](README_EN.md)

把浅色纸上的深色笔迹照片处理成透明底 PNG，可用于 Word、PDF 等文档。
图片在自己的浏览器内处理，不上传服务器。界面浅色、自包含，无 CDN、账号或服务端依赖。

## 使用

[下载源码](https://github.com/zengtianli/sig-workbench/archive/refs/heads/main.zip)，解压后用现代浏览器打开 `web/index.html` 即可抠图。
也可以从[公开源码仓库](https://github.com/zengtianli/sig-workbench)获取：

```sh
git clone https://github.com/zengtianli/sig-workbench.git
cd sig-workbench
```

也可以在源码根目录启动本地服务器，无需构建：

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

打开 <http://127.0.0.1:8000/web/>，拖入、选择或粘贴图片，下载透明底 PNG。
支持浏览器能解码的图片格式；HEIC 支持取决于浏览器，可先转为 JPG 或 PNG。
输出内嵌 300 dpi。可调整墨色、放大倍数、去噪与横线去除，阈值默认自动计算。

「我的签名库」保存在当前浏览器的 IndexedDB 中。此源码不含预置签名库。
换设备、浏览器、无痕窗口或清除浏览器数据后，已存图片可能丢失，请自行导出备份。
直接打开文件时，存储行为因浏览器而异；本地服务器提供稳定的来源地址。
剪贴板功能还取决于浏览器权限和安全上下文，无法使用时可下载 PNG。

## 设置、快捷键和版本

顶部「设置与更新」提供配置 JSON 导出/导入。处理参数和两个选项保存在当前浏览器的
localStorage；配置文件不包含签名图片、账号或权限。Alt / Option + Shift + S 打开设置，
可关闭；输入控件内、Ctrl / Command 保留组合和重复按键不触发。浏览器或系统占用同一
组合时可用按钮。纯 Web 无 Apple 原生 iCloud 容器，换设备请导出/导入配置并备份图片。

「检查更新」实际读取同源 `version.json`，获取新版入口重新载入原页面，保留配置和
IndexedDB。自动检查默认关闭，可选择每次打开时检查；网络错误或坏版本信息会显示失败。
直接打开 file:// 时浏览器可能禁止 fetch，请按上面方法使用本地服务器。

可用 Node 读取导出的同一配置格式或检查当前源码版本，不读取用户浏览器目录：

```sh
node tools/sig_config.cjs config status --config ./exported-sig.json --json
node tools/sig_config.cjs config import --config ./portable-sig.json --input ./exported-sig.json --json
node tools/sig_config.cjs update check --json
```

完整 Agent 入口为 `bin/sig`，无需常驻服务。先按下方步骤准备 Python 环境，设
`SIG_PYTHON=.venv/bin/python`；Chrome/Chromium 用于实际网页工作区，可用 `CHROME` 指定路径。

```sh
SIG_PYTHON=.venv/bin/python bin/sig status --json
SIG_PYTHON=.venv/bin/python bin/sig extract test/fixtures/sig-a.png --output sample.png --json
SIG_PYTHON=.venv/bin/python bin/sig workspace add --profile ./sig-profile --input test/fixtures/sig-a.png --json
SIG_PYTHON=.venv/bin/python bin/sig workspace export --profile ./sig-profile --output signatures.zip --json
```

工作区复用真实网页 IndexedDB，提供 list、rename、remove、clear、config-import/config-export、update；
删除需 `--yes`。`--profile` 必须是新空目录或本工具拥有的目录，拒绝读取普通浏览器配置。
配置导出与网页相同，但工作区独立于日常浏览器，可通过网页 JSON 和导出的 PNG 迁移。
原网页的系统剪贴板与实际按键仍仅由本人在窗口中操作。成功/失败 JSON 分别有 ok:true 与
ok:false/error，退出码为 0 成功、1 操作失败、2 用法错误。

## 可选 Python 命令行

需要 Python 3.10 或更新版本。网页版不需要这些依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python engine/sig_extract.py test/fixtures/sig-a.png -o output --preview
```

可以传入多张图片，加 `--deline` 去除横线，用 `--ink blue` 更改墨色。
虚构示例仅用于算法验证，不是任何人的签名。

## 验证与开发

Python 与浏览器分别实现相同算法：背景归一化、Otsu 阈值、软 alpha、去噪、
可选横线去除与竖笔桥接、裁边和着色。修改算法时，核对两份实现并运行：

```sh
PYTHON=.venv/bin/python ./verify.sh
```

验证需要 Google Chrome 或兼容的 Chromium。脚本会寻找常用可执行文件，
也可用 `CHROME=/path/to/chromium` 指定。只启动隐藏的无头浏览器，
使用独立临时目录；数值对账与真实页面加载测试并行执行。
对账要求 Otsu 阈值差不超过 3、墨占比差不超过 0.6 个百分点，
并检查横线去除的实际差分。页面测试覆盖图片处理、双预览、操作按钮、
300 dpi PNG 与浏览器本地存储，不读取用户文件或系统剪贴板。

测试图由 `test/generate_fixtures.py` 从数学曲线生成，全部为虚构笔迹。
可用 `.venv/bin/python test/generate_fixtures.py` 重建。
浏览器核心须保持 IIFE 包裹，仅导出 `window.SigCore`，避免污染全局名称。

这是一份从私有开发位置单向导出的源码快照，不包含私有历史、作者素材、部署配置或访问闸。
后续快照按需更新。浏览器工具直接从源码使用，无需安装包。

## 许可

原创代码采用 [MIT](LICENSE)。依赖说明见 [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES.md)。
