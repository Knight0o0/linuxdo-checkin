# LinuxDo 每日签到（每日打卡）

自动登录 [LinuxDo](https://linux.do/) 并完成每日签到任务，支持随机浏览帖子、点赞、极低概率自动回复，以及多种推送通知方式。

当前主要实现方式：
- 使用 **DrissionPage** + **curl_cffi** 进行浏览器自动化和请求伪装
- 支持 **GitHub Actions** 和 **青龙面板** 定时运行
- 推送渠道：Telegram / Gotify / Server酱³ / WxPusher（官方接口）

**注意**：自动回复概率已调至极低（约 6.5%），回复内容均为常见礼貌短语，旨在轻度增加活跃度。如不需要可直接注释掉相关代码。

## 功能清单

- 自动登录 LinuxDo 账号
- 显示 Connect 信息（连接数、要求等）
- 随机浏览若干帖子（模拟滚动、随机点赞）
- 极低概率自动回复（保守短语，避免风控）
- 支持以下通知渠道（可同时启用多个）：
  - Telegram
  - Gotify
  - Server酱³
  - WxPusher（标准官方 API）

## 环境变量配置

### 必填变量

| 变量名                | 说明                        | 示例值                             |
|-----------------------|-----------------------------|------------------------------------|
| `LINUXDO_USERNAME`    | LinuxDo 用户名或邮箱        | `yourname` 或 `xxx@gmail.com`      |
| `LINUXDO_PASSWORD`    | LinuxDo 登录密码            | `your_password`                    |

**兼容写法**：若未设置以上两个变量，脚本会自动读取旧的 `USERNAME` 和 `PASSWORD`（但建议统一使用新名称）。

### 可选变量

| 变量名                   | 说明                              | 示例值                                      | 备注                             |
|--------------------------|-----------------------------------|---------------------------------------------|----------------------------------|
| `BROWSE_ENABLED`         | 是否执行浏览/点赞/回复任务        | `true` / `false` （默认 `true`）            | 关闭后只登录不浏览               |
| `GOTIFY_URL`             | Gotify 服务器地址                 | `https://push.yourdomain.com`               |                                  |
| `GOTIFY_TOKEN`           | Gotify 应用 Token                 | `Axxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`           |                                  |
| `SC3_PUSH_KEY`           | Server酱³ SendKey                 | `sctxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`         |                                  |
| `WXPUSHER_APP_TOKEN`     | WxPusher 应用 Token               | `AT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`       | 必须是 AT_ 开头的官方 token     |
| `WXPUSHER_TOPIC_IDS`     | WxPusher 推送的主题ID（逗号分隔） | `1234,5678,9012`                            | 可同时推送到多个主题             |
| `TELEGRAM_TOKEN`         | Telegram Bot Token                | `123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxx`     | 通过 @BotFather 获取             |
| `TELEGRAM_USERID`        | Telegram 接收者 chat_id           | `123456789` 或 `-1001234567890`（群组）     | 通过 @userinfobot 获取           |

## 部署方式

### 1. GitHub Actions

1. Fork 本仓库
2. 进入 **Settings → Secrets and variables → Actions → New repository secret**
3. 添加上述必填 + 你需要的可选变量
4. 工作流默认每 6 小时运行一次（可修改 `.github/workflows/*.yml` 中的 cron 表达式）

**查看运行日志**：
- Actions → 选择 `LinuxDo Daily Check-in` → 点开最新运行记录 → 查看 `run_script` 步骤
- 可看到登录状态、Connect Info、浏览记录、推送结果等

### 2. 青龙面板（推荐使用 debian 镜像）

**推荐镜像**：`whyour/qinglong:debian` （alpine 版缺少部分依赖，安装 chromium 容易失败）

#### 步骤

1. **安装 Python 依赖**

   青龙面板 → 依赖管理 → Python3 → 一次性安装以下全部依赖：
DrissionPage==4.1.0.18
wcwidth==0.2.13
tabulate==0.9.0
loguru==0.7.2
curl-cffi
beautifulsoup4
text2. **安装系统依赖（chromium）**

青龙面板 → 依赖管理 → Linux → 搜索并安装 `chromium`

若失败，可进入容器手动执行：

```bash
apt update && apt install -y chromium

添加订阅青龙 → 订阅管理 → 新建订阅
名称：任意（建议：LinuxDo 签到）
类型：公开仓库
链接：https://github.com/你的用户名/linuxdo-checkin.git （替换为你的 fork 地址）
分支：main
定时规则：0 0 * * * （每天 0 点更新一次上游代码）

添加环境变量青龙 → 环境变量 → 新建变量，按上方表格逐一添加
运行与查看日志订阅拉取完成后 → 定时任务 → 找到对应任务 → 手动运行 → 查看日志

常见问题
Q：登录总是失败？
A：常见原因及解决：

账号密码错误 → 浏览器手动登录确认
触发风控 → 等待一段时间或换 IP 再试
网络问题 → 检查容器/ Actions 网络
多次运行通常能成功（脚本内置重试）

Q：Connect Info 一直是空的？
A：新号需要积累活跃度（发帖、回复、浏览等），多挂几天一般就会显示。
Q：想完全关闭自动回复？
A：打开脚本文件，找到 click_one_topic 方法中这一行：
Pythonif random.random() < 0.065:
    self.auto_reply(tab)
注释掉或把 0.065 改成 0.001 即可基本关闭。
Q：推送失败但签到成功？
A：推送失败不会影响签到本身，仅记录错误日志。检查对应服务的 Token / URL / ID 是否正确。
鸣谢

DrissionPage 项目
curl-cffi 提供的指纹伪装能力
所有提交 issue / PR / 分享经验的朋友

最后祝大家签到稳定，早日达到心仪的 Trust Level ～
最后更新：2026 年 1 月
