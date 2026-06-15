# UnmaskZip

> 层层剥开伪装的压缩包 — 支持 AES 加密 ZIP、拼接伪装（视频/图片+ZIP）、递归解压直达最终内容。

## ✨ 功能

- 🔓 **AES-256 加密 ZIP** 支持（pyzipper 内置）
- 🎭 **拼接伪装识别** — 自动识别 .mp4/.jpg 等伪装成媒体文件的压缩包
- 🔄 **递归解压** — 解出的内层压缩包继续剥，直到最终内容
- 📦 **智能整理** — 单文件/单文件夹自动平铺，多文件按原文件名建子目录
- 🖥️ **GUI 拖拽界面** — 拖文件/文件夹进列表，每文件独立状态显示
- 🔧 **多引擎回退** — pyzipper → 7-Zip → WinRAR 按排序依次尝试
- 🧹 **可选清理中间文件** — mp4→jpg→最终文件，自动删除中间产物
- 🔐 **Fernet 加密密码本** — 密码加密存储，支持 txt 导入导出

## 📦 安装

```bash
git clone https://github.com/yayouren/UnmaskZip.git
cd UnmaskZip
pip install -r requirements.txt
python UnmaskZip.py
```

或直接下载 [Releases](../../releases) 中的 `UnmaskZip.exe` 免安装运行。

## 🚀 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "UnmaskZip" ^
  --hidden-import pyzipper --hidden-import cryptography --hidden-import tkinterdnd2 ^
  UnmaskZip.py
```

## 📖 使用

1. 打开软件 → 菜单栏 **密码本** → 填入密码
2. 拖拽文件/文件夹到列表，或点「添加文件」
3. 勾选「解压到同目录」或走默认 `_extracted` 文件夹
4. 可选「覆盖解压」「清理中间文件」
5. 点 **开始解压**

**设置** 中可调整解压引擎排序（pyzipper / 7-Zip / WinRAR），分别配置路径，扫描自动识别。

## 🔧 依赖

- Python 3.10+
- pyzipper
- cryptography
- tkinterdnd2

## 📄 License

MIT
