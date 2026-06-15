# UnmaskZip

> 层层剥开伪装的压缩包，支持 AES 加密 ZIP、拼接伪装文件（视频/图片 + ZIP），递归解压直达最终内容。

## 功能

- 🔓 支持 **AES-256 加密 ZIP**（pyzipper）
- 🎭 自动识别**拼接伪装**（.mp4/.jpg + ZIP 合并的文件）
- 🔄 **递归解压** — 解出的文件如果还是压缩包，继续剥
- 📦 智能整理 — 单文件平铺，多文件建子目录，同名文件夹自动合并
- 🖥️ GUI 界面 — 拖拽添加、每文件状态、进度条、日志折叠
- 🔧 自动调用系统 **7-Zip / WinRAR** 作为回退方案
- 🔐 密码本 **Fernet 加密**存储，支持导入导出

## 截图

![主界面](screenshots/main.png)

## 安装

```bash
git clone https://github.com/yayouren/UnmaskZip.git
cd UnmaskZip
pip install -r requirements.txt
python UnmaskZip.py
```

## 打包为 exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "UnmaskZip" --hidden-import pyzipper --hidden-import cryptography --hidden-import tkinterdnd2 UnmaskZip.py
```

## 使用

1. 打开软件，菜单栏 → **密码本** → 添加密码
2. 拖拽文件/文件夹到文件列表，或点「添加文件」
3. 勾选「解压到同目录」或走默认 `_extracted` 文件夹
4. 点「开始解压」

## 依赖

- Python 3.10+
- pyzipper
- cryptography
- tkinterdnd2
- tkinter（内置）

## License

MIT
