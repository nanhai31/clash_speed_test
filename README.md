# clash_speed_test
测试用，侵权删
# Clash 节点自动测速工具

自动从远程URL获取Clash配置文件，测试节点速度，并生成优化后的配置文件。

## 功能特性

- ✅ 自动从URL下载Clash配置
- ✅ 并行测试节点延迟（TCP/HTTP两种模式）
- ✅ 智能筛选低延迟节点
- ✅ 定时自动运行（GitHub Actions）
- ✅ 自动提交更新到仓库
- ✅ 支持手动触发运行
- ✅ 生成详细的统计信息

## 使用方法

### 1. Fork 本仓库

点击右上角的 "Fork" 按钮，将本仓库复制到你的账户下。

### 2. 配置 Secrets

在你的仓库中，进入 `Settings` → `Secrets and variables` → `Actions`，添加以下 Secret：

| Secret名称 | 必填 | 说明 | 示例 |
|-----------|------|------|------|
| `CONFIG_URL` | 是 | Clash配置文件的URL | `https://example.com/config.yaml` |

### 3. 自动运行

工作流会在每天北京时间凌晨2点自动运行。你也可以：

- 进入 `Actions` 选项卡
- 选择 `Clash Node Speed Test` 工作流
- 点击 `Run workflow` 手动触发

### 4. 获取优化后的配置

优化后的配置文件位于：
- `config/fast_config.yaml` - 优化后的Clash配置
- `config/fast_config_stats.json` - 统计信息

## 配置参数

可以通过手动触发工作流时修改以下参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `max_latency` | 最大延迟阈值（毫秒） | 500 |
| `top_n` | 保留前N个最快节点（留空保留所有） | 空 |
| `use_http` | 使用HTTP测试（更准确） | true |
| `test_url` | 测试用的URL | http://www.google.com/generate_204 |

## 本地运行
