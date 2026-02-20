# Windows Release 发布检查清单

## 发布前检查

### 1. 代码准备
- [ ] 更新 `pyproject.toml` 中的版本号
- [ ] 更新 `docs/CHANGELOG.md` 添加本次更新内容
- [ ] 运行 `pytest -q` 确保所有测试通过
- [ ] 运行 `ruff check .` 确保代码规范检查通过

### 2. 构建测试
- [ ] 运行 `build_windows.bat` 构建可执行文件
- [ ] 运行 `test_build.bat` 测试构建结果
- [ ] 在干净的 Windows 系统上测试运行（建议使用虚拟机）

### 3. 功能测试
- [ ] 测试 `image-gen-test.exe` 基本命令
  - [ ] `--help`
  - [ ] `--version`
  - [ ] `single` 命令
  - [ ] `compare` 命令
  - [ ] `batch` 命令
  - [ ] `models` 命令
  - [ ] `history` 命令

- [ ] 测试 `igt-tui.exe` 基本功能
  - [ ] 启动 TUI 界面
  - [ ] 测试 Generate 标签页
  - [ ] 测试 Video 标签页（如果需要）
  - [ ] 测试 Speech 标签页（如果需要）
  - [ ] 测试 Models 标签页
  - [ ] 测试 History 标签页
  - [ ] 测试 Config 标签页

### 4. 配置文件测试
- [ ] 复制 `.env.example` 到 `.env`
- [ ] 配置至少一个 provider 的 API key
- [ ] 运行一次完整的生成流程
- [ ] 检查 `runs/` 目录输出是否正常

### 5. 打包发布
- [ ] 运行 `package_release.bat` 创建发布包
- [ ] 检查 ZIP 包内容是否完整
- [ ] 解压 ZIP 包到新位置进行最终测试

## GitHub Release 创建步骤

### 1. 创建 Git Tag
```cmd
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

### 2. 在 GitHub 创建 Release
1. 访问项目的 Releases 页面
2. 点击 "Draft a new release"
3. 填写信息：
   - **Tag**: `v0.1.0`
   - **Title**: `Windows v0.1.0`
   - **Description**: 从 CHANGELOG.md 复制
   - **Assets**: 上传 `image-gen-test-tool-windows-v0.1.0.zip`

### 3. Release 说明模板
```markdown
## Image Generation Test Tool v0.1.0 - Windows Release

### 下载
- [image-gen-test-tool-windows-v0.1.0.zip](https://github.com/xxx/releases/download/v0.1.0/image-gen-test-tool-windows-v0.1.0.zip)

### 快速开始
1. 解压 ZIP 文件
2. 复制 `.env.example` 到 `.env`
3. 编辑 `.env` 添加您的 API keys
4. 运行：
   - `image-gen-test.exe --help` (CLI 工具)
   - `igt-tui.exe` (TUI 界面)

### 更新内容
- 从 CHANGELOG.md 复制

### 系统要求
- Windows 10 或更高版本
- 不需要安装 Python

### 已知问题
- 杀毒软件可能误报（PyInstaller 打包程序的常见问题）
- TUI 界面建议使用 Windows Terminal 以获得最佳体验
```

### 4. 发布
点击 "Publish release" 按钮

## 发布后验证

### 1. 下载测试
- [ ] 从 GitHub Release 下载 ZIP 包
- [ ] 在不同 Windows 版本上测试（Win10/Win11）
- [ ] 在干净系统上测试（无 Python 环境）

### 2. 文档更新
- [ ] 更新 README.md 中的下载链接
- [ ] 更新版本号说明
- [ ] 添加使用截图（可选）

### 3. 问题跟踪
- [ ] 监控 GitHub Issues
- [ ] 收集用户反馈
- [ ] 记录常见问题到文档

## 常见问题处理

### 杀毒软件误报
**解决方案**：
- 在 Release 中添加说明
- 提供文件哈希值供验证
- 考虑购买代码签名证书

### 依赖缺失
**解决方案**：
- 使用 `Dependency Walker` 检查缺失的 DLL
- 在 `build_exe.spec` 中添加缺失的依赖
- 重新构建

### TUI 显示问题
**解决方案**：
- 建议用户使用 Windows Terminal
- 在文档中说明终端要求
- 提供纯 CLI 的替代方案

## 版本号规则

遵循语义化版本（Semantic Versioning）：`MAJOR.MINOR.PATCH`

- **MAJOR**: 不兼容的 API 变更
- **MINOR**: 向下兼容的新功能
- **PATCH**: 向下兼容的 Bug 修复

示例：
- `0.1.0` - 初始发布
- `0.1.1` - Bug 修复
- `0.2.0` - 新增功能
- `1.0.0` - 稳定版本
