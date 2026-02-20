# Windows 构建快速指南

## 🚀 一键构建

### 推荐：构建独立 TUI 程序

```cmd
# 1. 进入项目目录
cd C:\Users\serow\Desktop\image-gen-test-tool

# 2. 安装依赖
pip install pyinstaller
pip install -e .[tui]

# 3. 构建独立 TUI
pyinstaller docs/build-scripts/build_tui.spec --clean --noconfirm

# 4. 运行
dist\igt-tui.exe
```

### 构建 CLI + TUI 完整包

```cmd
# 使用批处理脚本（推荐）
cd C:\Users\serow\Desktop\image-gen-test-tool
docs\build-scripts\build_windows.bat

# 或手动构建
pyinstaller docs/build-scripts/build_final.spec --clean --noconfirm
```

## 📦 构建产物

构建成功后：
- **独立 TUI**: `dist\igt-tui.exe` (24 MB)
- **完整包**: `dist\image-gen-test-tool\` (包含 CLI + TUI)

## 🔧 快速修复

### TUI 无法启动

使用 `build_tui.spec` 而不是 `build_exe.spec`：

```cmd
pyinstaller docs/build-scripts/build_tui.spec --clean --noconfirm
```

### 目录被占用

```cmd
taskkill /F /IM igt-tui.exe 2>nul
taskkill /F /IM image-gen-test.exe 2>nul
```

## 📝 详细文档

- [完整构建文档](README.md)
- [Windows 打包指南](../BUILD_WINDOWS.md)
- [发布检查清单](../guides/windows-release-checklist.md)
