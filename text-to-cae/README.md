# Text to CAE 使用教程

Text to CAE 是一个本地运行的 Abaqus 仿真工作区。它把三件事连在一起：

1. 用 Codex、Cursor、Claude Desktop 等 AI 客户端编写或修改 Abaqus 仿真脚本。
2. 通过 [Abaqus MCP](https://github.com/Cai-aa/abaqus-mcp) 连接 AI 客户端和 Abaqus/CAE。
3. 用本项目自带的浏览器 viewer 查看 Abaqus 仿真结果、动态过程、云图、模型树和参数。

项目仓库：

```text
https://github.com/Cai-aa/text-to-cae
```

配套 Abaqus MCP 仓库：

```text
https://github.com/Cai-aa/abaqus-mcp
```

## 1. 推荐工作流：Codex + Abaqus MCP + Codex浏览器结果查看

推荐的完整使用方式如下：

```text
Codex
  -> 通过 Abaqus MCP 连接 Abaqus/CAE
  -> 在 Codex 中编写或修改 Abaqus Python 仿真代码
  -> 让 Abaqus 执行建模、网格划分、提交作业、读取 ODB
  -> 导出 result_mesh.json
  -> 在 text-to-cae 浏览器 viewer 中查看仿真结果
```

这个流程的好处是：

- Codex 负责自然语言理解、代码修改、脚本调试和自动化执行。
- Abaqus/CAE 负责真实建模、求解和 ODB 结果生成。
- text-to-cae viewer 负责用浏览器交互式查看结果。

## 2. 在 Codex 中联通 Abaqus

### 2.1 安装 Abaqus MCP

先克隆 Abaqus MCP：

```powershell
git clone https://github.com/Cai-aa/abaqus-mcp.git $env:USERPROFILE\.abaqus-mcp
```

安装 MCP server 依赖：

```powershell
pip install mcp
```

如果你使用虚拟环境、Conda、uv 或 Codex 自带 Python，把 `mcp` 安装到对应 Python 环境即可。

### 2.2 让 Abaqus/CAE 加载 MCP 插件

复制 Abaqus 启动环境文件：

```powershell
Copy-Item -Force "$env:USERPROFILE\.abaqus-mcp\abaqus_v6.env.example" "$env:USERPROFILE\abaqus_v6.env"
```

也可以安装 Abaqus GUI 菜单插件：

```powershell
Copy-Item -Recurse -Force "$env:USERPROFILE\.abaqus-mcp\abaqus_plugins\mcp_control" "$env:USERPROFILE\abaqus_plugins\mcp_control"
```

重启 Abaqus/CAE 后，可以在菜单中看到：

```text
Plug-ins -> MCP
```

### 2.3 配置 Codex 使用 Abaqus MCP

在支持 MCP 的 Codex 环境中，把 Abaqus MCP server 配成类似下面的形式：

```json
{
  "mcpServers": {
    "abaqus-mcp": {
      "command": "python",
      "args": ["C:/Users/<your-user>/.abaqus-mcp/mcp_server.py"]
    }
  }
}
```

把 `<your-user>` 改成你的 Windows 用户名。如果 Python 不在 PATH 中，可以把 `command` 改成 Python 解释器的绝对路径。

Cursor、Claude Desktop 等其他支持 MCP 的客户端也可以使用同样的 MCP server 配置。

### 2.4 在 Abaqus 中启动 MCP 连接

打开 Abaqus/CAE 后，可以通过菜单启动：

```text
Plug-ins -> MCP -> Start MCP
```

也可以在 Abaqus Python 控制台中启动：

```python
mcp_start()
```

如果 Abaqus 版本对后台线程支持不稳定，可以使用 cooperative 或 blocking 模式：

```python
mcp_coop_loop()
```

或：

```python
mcp_loop()
```

### 2.5 在 Codex 中操作 Abaqus

连接成功后，可以直接在 Codex 中提出任务，例如：

```text
连接当前 Abaqus/CAE，运行 text-to-cae 的球冲击板材案例，提交作业，导出 result_mesh.json，并告诉我峰值应力和最大位移。
```

```text
修改三维铣削案例：工件尺寸改大，刀具直径改为 8 mm，重新生成可在浏览器查看的 result_mesh.json。
```

```text
读取当前 Abaqus ODB，列出所有 step、frame、instance，并截取当前 viewport。
```

```text
帮我写一个新的 Abaqus Python 脚本：创建带孔板拉伸模型，定义材料、边界条件、网格、作业，并导出浏览器 viewer 可读取的结果文件。
```

Codex 可以通过 MCP 做这些事情：

- 查询当前 Abaqus 模型。
- 创建 part、material、section、step、load、BC、interaction。
- 执行 Abaqus Python 脚本。
- 提交 job。
- 打开并读取 ODB。
- 获取 Abaqus message log。
- 截取 Abaqus viewport。
- 导出 `result_mesh.json`，供本项目 viewer 展示。

## 3. 在浏览器中查看 Abaqus 仿真结果

### 3.1 安装前端依赖

克隆本项目：

```powershell
git clone https://github.com/Cai-aa/text-to-cae.git
Set-Location .\text-to-cae
```

安装 viewer 依赖：

```powershell
Set-Location .\viewer
npm.cmd install
```

### 3.2 启动 viewer

```powershell
npm.cmd run dev
```

默认打开：

```text
http://127.0.0.1:4178/
```

如果端口被占用，可以指定端口：

```powershell
$env:VIEWER_PORT = "4181"
npm.cmd run dev
```

然后打开：

```text
http://127.0.0.1:4181/
```

### 3.3 打开指定案例

```text
http://127.0.0.1:4178/?case=cantilever
http://127.0.0.1:4178/?case=hole-plate
http://127.0.0.1:4178/?case=hole-plate-modal
http://127.0.0.1:4178/?case=sphere-impact
http://127.0.0.1:4178/?case=milling-3d
http://127.0.0.1:4178/?case=bullet-plate
```

进入 Abaqus 风格界面：

```text
http://127.0.0.1:4178/?case=sphere-impact&mode=cae
```

### 3.4 从 Abaqus 到浏览器的结果链路

一个案例通常会生成：

```text
models/<case>/
  cae_parameters.json
  cae_project.json
  <case>_abaqus.py
  export_*.py
  result_mesh.json
```

其中：

- `*_abaqus.py` 负责在 Abaqus 中建模、划分网格、提交作业。
- `export_*.py` 负责从 ODB 导出浏览器能读取的网格、云图、动态帧。
- `result_mesh.json` 是 viewer 实际加载的结果文件。
- `cae_project.json` 是模型树、状态、结果指标和项目描述。
- `cae_parameters.json` 是可编辑参数。

重新求解或导出后，在浏览器中点击右侧“刷新”，或刷新页面，就能看到新的 Abaqus 结果。

## 4. 通过浏览器直接运行 Abaqus

viewer 自带本地接口，可以在浏览器里修改参数并触发 Abaqus 重新求解。

如果 Abaqus 不在默认路径，启动 viewer 前设置：

```powershell
$env:ABAQUS_COMMAND = "C:\SIMULIA\Commands\abaqus.bat"
npm.cmd run dev
```

默认路径是：

```text
G:\SIMULIA\Commands\abaqus.bat
```

浏览器中的运行链路是：

```text
viewer
  -> /__cae/run
  -> Abaqus noGUI
  -> *_abaqus.py
  -> export_*.py
  -> result_mesh.json
  -> viewer 刷新结果
```

## 5. 界面操作说明

页面主要分为三块：

- 左侧模型树：展示项目、零件、材料、装配、分析步、载荷、边界条件、网格、作业和结果。
- 中间三维视窗：显示 Abaqus 风格结果云图、网格边线、动态帧、刀具、球、弹体等对象。
- 右侧参数和结果面板：显示状态、结果指标、可编辑参数和运行按钮。

顶部工具条：

- `播放`：播放动态结果帧。
- `速度 0.5x / 1x / 2x`：调整播放速度。
- 时间帧滑条：查看某一时刻。
- `Abaqus / 深色 / 浅色`：切换显示风格。

鼠标操作：

- 左键拖动：旋转模型。
- 中键拖动：平移模型。
- 滚轮：缩放模型。

## 6. 案例说明

### 6.1 悬臂梁

目录：

```text
models/text-to-cae
```

静力学入门案例，展示悬臂梁位移和应力云图。

### 6.2 带孔板拉伸

目录：

```text
models/text-to-cae-hole-plate
```

展示带圆孔板在拉伸载荷下的应力集中。

### 6.3 带孔板模态

目录：

```text
models/text-to-cae-hole-plate-modal
```

展示模态分析结果，可在 viewer 中查看不同阶振型。

### 6.4 球冲击板材

目录：

```text
models/text-to-cae-sphere-impact
```

展示钢球冲击固支板材的显式动力学过程。当前版本包含更真实的球-板接触可视化：

- 钢球以初速度冲击板面。
- 板材中心形成连续圆形压痕。
- 接触核和外圈弯曲区域有应力集中。
- 回弹阶段球与板材不穿模。

关键文件：

- `sphere_impact_abaqus.py`
- `export_dynamic_mesh.py`
- `refresh_contact_result.mjs`

刷新当前展示数据：

```powershell
node models\text-to-cae-sphere-impact\refresh_contact_result.mjs
```

### 6.5 三维铣削动力学

目录：

```text
models/text-to-cae-milling-3d
```

展示端铣刀切削工件的三维动态过程。当前版本对可视化做了修正：

- 工件尺寸更大。
- 网格更细。
- 切削槽按刀具直径生成。
- 切削后槽为长方形平底槽。
- 不再用分层变形假装材料去除。

由于铣削 `result_mesh.json` 超过 GitHub 单文件限制，仓库中不上传该文件。克隆后如需查看铣削结果，可以重新运行：

```powershell
node models\text-to-cae-milling-3d\refresh_visual_result.mjs
```

### 6.6 弹体侵彻板材

目录：

```text
models/text-to-cae-bullet-plate
```

展示弹体高速侵彻板材的三维显式动力学过程。大型 ODB 文件没有上传到 GitHub，需要本地 Abaqus 重新求解。

## 7. 直接运行 Abaqus 脚本

也可以不通过浏览器，直接在命令行运行案例。

球冲击板材：

```powershell
& "G:\SIMULIA\Commands\abaqus.bat" cae noGUI=models\text-to-cae-sphere-impact\sphere_impact_abaqus.py
& "G:\SIMULIA\Commands\abaqus.bat" cae noGUI=models\text-to-cae-sphere-impact\export_dynamic_mesh.py
```

三维铣削：

```powershell
& "G:\SIMULIA\Commands\abaqus.bat" cae noGUI=models\text-to-cae-milling-3d\milling_abaqus.py
& "G:\SIMULIA\Commands\abaqus.bat" cae noGUI=models\text-to-cae-milling-3d\export_milling_mesh.py
```

## 8. 文件结构

```text
text-to-cae/
  README.md
  models/
    text-to-cae/
    text-to-cae-hole-plate/
    text-to-cae-hole-plate-modal/
    text-to-cae-sphere-impact/
    text-to-cae-milling-3d/
    text-to-cae-bullet-plate/
  viewer/
    package.json
    vite.config.mjs
    main.jsx
    components/
      CaeResultViewer.js
      TextToCaeWorkspace.js
```

## 9. GitHub 和大文件说明

本仓库公开发布：

```text
https://github.com/Cai-aa/text-to-cae
```

以下内容不会提交到 GitHub：

- `viewer/node_modules/`
- `viewer/dist/`
- Abaqus `.odb`
- Abaqus `.inp`
- Abaqus 中间文件，例如 `.sim`、`.dat`、`.msg`、`.sta`
- Python `__pycache__`
- 正交切削旧案例目录
- 超过 100MB 的铣削 `result_mesh.json`

这些文件可以通过安装依赖或重新运行 Abaqus 脚本生成。

## 10. 隐私与公开仓库检查

公开前建议检查：

```powershell
git status
git ls-files
```

本仓库不应包含：

- GitHub token、API key、密码或私钥。
- 本机用户目录绝对路径。
- Abaqus 商业求解生成的大型 ODB。
- `node_modules`、`dist` 等可重新生成目录。

如果误提交了敏感内容，不要只在最新 commit 中删除，应使用 GitHub secret scanning、吊销对应 token，并清理 Git 历史。

## 11. 常见问题

### 页面打不开

确认 dev server 是否启动：

```powershell
Set-Location .\viewer
npm.cmd run dev
```

然后访问终端显示的端口，例如：

```text
http://127.0.0.1:4178/
```

### 修改结果文件后页面没变

点击右侧“刷新”，或直接刷新浏览器页面。`result_mesh.json` 是运行时读取的，旧页面可能还缓存着上一帧数据。

### 点击运行后 Abaqus 不启动

检查 `ABAQUS_COMMAND` 是否指向正确的 Abaqus 命令脚本：

```powershell
$env:ABAQUS_COMMAND
```

如果为空或路径不对，重新设置：

```powershell
$env:ABAQUS_COMMAND = "G:\SIMULIA\Commands\abaqus.bat"
npm.cmd run dev
```

### GitHub clone 后缺少某些结果

大型 ODB、INP 和超大 `result_mesh.json` 没有上传。需要重新运行对应 Abaqus 脚本或刷新脚本。

### 构建前端

```powershell
Set-Location .\viewer
npm.cmd run build
```

构建产物会写入 `viewer/dist/`，该目录不会提交到 Git。
