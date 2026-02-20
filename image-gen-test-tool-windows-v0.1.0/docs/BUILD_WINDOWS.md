# Windows 可执行程序打包指南

本文档说明如何将项目打包为 Windows 可执行程序（.exe）用于发布。

## 前置要求

- Python 3.11+
- Windows 10 或更高版本
- 管理员权限（用于安装依赖）

## 快速开始

### 方法一：使用自动化脚本（推荐）

1. **构建可执行文件**
   ```cmd
   build_windows.bat
   ```

   这个脚本会自动：
   - 检查 Python 版本
   - 安装 PyInstaller
   - 安装项目依赖
   - 清理旧的构建
   - 构建新的可执行文件

2. **打包发布版本**
   ```cmd
   package_release.bat
   ```

   这个脚本会自动：
   - 将可执行文件打包到发布目录
   - 复制文档和配置文件
   - 创建 ZIP 压缩包

### 方法二：手动构建

1. **安装 PyInstaller**
   ```cmd
   pip install pyinstaller
   ```

2. **安装项目依赖（包括 TUI）**
   ```cmd
   pip install -e .[tui,build]
   ```

3. **构建可执行文件**
   ```cmd
   pyinstaller build_exe.spec --clean --noconfirm
   ```

4. **查看构建结果**
   构建产物位于 `dist/image-gen-test-tool/` 目录

## 构建产物说明

### 目录结构
```
dist/image-gen-test-tool/
├── image-gen-test.exe      # CLI 工具主程序
├── igt-tui.exe             # TUI 界面主程序
├── _internal/              # 依赖库和资源文件
│   ├── Python DLLs
│   ├── 依赖包
│   └── 数据文件
├── .env.example            # 环境变量模板
├── custom_models.json      # 自定义模型配置
├── extra.example.json      # 额外参数示例
└── prompts.txt             # 批量提示词示例
```

### 可执行文件说明

| 文件 | 说明 | 使用场景 |
|------|------|----------|
| `image-gen-test.exe` | CLI 命令行工具 | 脚本自动化、批处理 |
| `igt-tui.exe` | TUI 文本用户界面 | 交互式操作、可视化界面 |

## 打包配置详解

### `build_exe.spec` 文件

这是 PyInstaller 的配置文件，主要包含：

- **入口点**: `cli.py` 和 `ui/tui/main.py`
- **数据文件**: 配置文件、环境变量模板
- **隐藏导入**: 自动检测缺失的模块导入
- **排除模块**: 减小体积，排除不需要的包（如 tkinter、numpy）

### 重要配置项

```python
# 包含的数据文件
datas = [
    ('.env.example', '.'),
    ('custom_models.json', '.'),
    # ...
]

# 隐藏导入（自动检测可能遗漏的模块）
hiddenimports = [
    'pydantic',
    'pydantic_core',
    'textual',
    # ...
]

# 排除不需要的模块（减小体积）
excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
    # ...
]
```

## 发布流程

### 1. 版本更新

在 `pyproject.toml` 中更新版本号：

```toml
[project]
version = "0.2.0"  # 更新版本号
```

### 2. 构建和打包

```cmd
build_windows.bat
package_release.bat
```

### 3. 测试发布包

1. 解压 `image-gen-test-tool-windows-v0.1.0.zip`
2. 在新位置测试运行：
   ```cmd
   cd image-gen-test-tool-windows-v0.1.0
   copy .env.example .env
   # 编辑 .env 添加 API keys
   image-gen-test.exe --help
   igt-tui.exe
   ```

### 4. 创建 GitHub Release

1. 在 GitHub 上创建新的 Release：
   - Tag: `v0.1.0`
   - Title: `Windows v0.1.0`
   - Description: 从 `docs/CHANGELOG.md` 复制更新内容

2. 上传 `image-gen-test-tool-windows-v0.1.0.zip`

3. 发布 Release

## 常见问题

### Q1: 构建失败，提示模块找不到

**A**: 在 `build_exe.spec` 的 `hiddenimports` 中添加缺失的模块。

### Q2: 运行时提示找不到数据文件

**A**: 检查 `build_exe.spec` 的 `datas` 配置，确保所有必需的配置文件都已包含。

### Q3: 体积太大（超过 200MB）

**A**:
- 在 `excludes` 中添加更多不需要的包
- 使用 UPX 压缩（已在配置中启用）
- 考虑使用 Nuitka 替代 PyInstaller（体积更小）

### Q4: 杀毒软件报毒

**A**: 这是 PyInstaller 打包程序的常见问题：
- 在 Release 中说明使用 PyInstaller 打包
- 可以考虑代码签名证书（需要购买）
- 用户可以临时禁用杀毒软件或添加白名单

### Q5: TUI 界面显示异常

**A**: 确保 Windows 终端支持 ANSI 颜色：
- Windows 10 1903+ 原生支持
- 或使用 Windows Terminal

## 高级选项

### 单文件打包

如果需要单文件 exe（体积更大，启动更慢）：

1. 修改 `build_exe.spec`
2. 将 `COLLECT` 部分改为单个 `EXE`
3. 设置 `onefile=True`

### 添加图标

1. 准备 `.ico` 文件
2. 在 `build_exe.spec` 中添加：
   ```python
   icon='path/to/icon.ico'
   ```

### 代码签名

1. 购买代码签名证书
2. 在 `build_exe.spec` 中配置：
   ```python
   codesign_identity='Developer ID Application: Your Name'
   ```

## 相关文件

- `build_exe.spec` - PyInstaller 配置文件
- `build_windows.bat` - 自动构建脚本
- `package_release.bat` - 发布打包脚本
- `pyproject.toml` - 项目版本配置

## 参考资源

- [PyInstaller 官方文档](https://pyinstaller.org/)
- [PyInstaller Spec 文件详解](https://pyinstaller.org/en/stable/spec-files.html)
- [Windows 打包最佳实践](https://github.com/pyinstaller/pyinstaller/wiki/How-to-Build-a-Windows-Binary)
