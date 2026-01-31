"""
cron: 0 */6 * * *
new Env("Linux.Do 签到")
"""
import os
import random
import time
import functools
import sys
import re
from loguru import logger
from DrissionPage import ChromiumOptions, Chromium
from tabulate import tabulate
from curl_cffi import requests
from bs4 import BeautifulSoup

def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}"
                    )
                    if attempt < retries - 1:
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(
                            f"将在 {sleep_s:.2f}s 后重试 ({min_delay}-{max_delay}s 随机延迟)"
                        )
                        time.sleep(sleep_s)
            return None
        return wrapper
    return decorator


os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")

BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in [
    "false", "0", "off"
]

GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
SC3_PUSH_KEY = os.environ.get("SC3_PUSH_KEY")

WXPUSHER_APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN")
WXPUSHER_TOPIC_IDS_STR = os.environ.get("WXPUSHER_TOPIC_IDS", "")
WXPUSHER_TOPIC_IDS = [
    int(tid.strip()) for tid in WXPUSHER_TOPIC_IDS_STR.split(",")
    if tid.strip().isdigit()
] if WXPUSHER_TOPIC_IDS_STR else []

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_USERID = os.environ.get("TELEGRAM_USERID")

HOME_URL    = "https://linux.do/"
LOGIN_URL   = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL    = "https://linux.do/session/csrf"


# 自动回复内容池（低调、自然）
REPLY_POOL = [
    "感谢分享！学到了",
    "非常有帮助的帖子，收藏了",
    "思路很清晰，mark一下",
    "正好最近也在研究这个，谢谢楼主",
    "+1 期待后续更新",
    "干货满满，受教了",
    "这个方法不错，试试看",
    "楼主牛啊，膜拜",
    "简单易懂，适合新手",
    "已阅，感谢大佬",
    "顶一下，支持原创",
    "学习了，谢谢分享经验",
    "这个坑我也踩过，解法很实用",
    "mark，回头仔细看",
    "内容质量很高，建议置顶",
    "感谢楼主无私分享！",
    "涨知识了，谢谢",
    "很好的经验贴，学习了",
]


class LinuxDoBrowser:
    def __init__(self):
        from sys import platform
        if platform in ("linux", "linux2"):
            ua_platform = "X11; Linux x86_64"
        elif platform == "darwin":
            ua_platform = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            ua_platform = "Windows NT 10.0; Win64; x64"
        else:
            ua_platform = "X11; Linux x86_64"

        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
            .set_argument("--disable-dev-shm-usage")
        )
        co.set_user_agent(
            f"Mozilla/5.0 ({ua_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        self.used_replies = set()

    def login(self):
        logger.info("开始登录 Linux.do")

        # Step 1: 获取 CSRF
        logger.info("获取 CSRF token...")
        headers = {
            "User-Agent": self.session.headers["User-Agent"],
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        try:
            # 修改：使用 "chrome" 而非具体版本号，让 curl_cffi 自动选择当前支持的最新 Chrome 指纹
            r = self.session.get(CSRF_URL, headers=headers, impersonate="chrome")
            r.raise_for_status()
            csrf = r.json().get("csrf")
            if not csrf:
                logger.error("未能获取到 CSRF token")
                return False
            logger.info(f"CSRF 获取成功: {csrf[:8]}...")
        except Exception as e:
            logger.error(f"获取 CSRF 失败: {e}")
            return False

        # Step 2: 登录
        logger.info("提交登录请求...")
        login_headers = headers.copy()
        login_headers.update({
            "X-CSRF-Token": csrf,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://linux.do",
        })
        data = {
            "login": USERNAME,
            "password": PASSWORD,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }

        try:
            # 修改：同样使用 "chrome"
            resp = self.session.post(
                SESSION_URL, data=data, headers=login_headers, impersonate="chrome"
            )
            resp.raise_for_status()
            json_data = resp.json()
            if json_data.get("error"):
                logger.error(f"登录失败: {json_data.get('error')}")
                return False
            logger.info("登录成功")
        except Exception as e:
            logger.error(f"登录请求异常: {e}")
            return False

        self.print_connect_info()

        # 同步 cookie 到 DrissionPage
        logger.info("同步 cookie 到浏览器...")
        cookies = [
            {"name": k, "value": v, "domain": ".linux.do", "path": "/"}
            for k, v in self.session.cookies.get_dict().items()
        ]
        self.page.set.cookies(cookies)
        self.page.get(HOME_URL)
        time.sleep(random.uniform(4, 7))

        # 验证登录状态
        if self.page.ele("@id=current-user") or "avatar" in self.page.html.lower():
            logger.info("登录状态验证通过")
            return True
        else:
            logger.warning("登录后未检测到用户元素，可能登录失败")
            return False

    def click_topic(self):
        if not BROWSE_ENABLED:
            return True

        try:
            topics = self.page.ele("@id=list-area").eles("tag:a[class*='title']")
            if not topics:
                logger.warning("首页未找到可点击的主题")
                return False

            selected = random.sample(topics, min(10, len(topics)))
            logger.info(f"随机选择 {len(selected)} 个帖子进行浏览")

            for topic in selected:
                href = topic.attr("href")
                if href and href.startswith("/"):
                    full_url = "https://linux.do" + href
                    self.click_one_topic(full_url)
                elif href and "http" in href:
                    self.click_one_topic(href)

            return True
        except Exception as e:
            logger.error(f"点击主题列表失败: {e}")
            return False

    @retry_decorator(retries=2, min_delay=3, max_delay=8)
    def click_one_topic(self, url):
        tab = self.browser.new_tab()
        try:
            tab.get(url)
            time.sleep(random.uniform(1.5, 3.5))

            if random.random() < 0.28:
                self.click_like(tab)

            if random.random() < 0.065:
                self.auto_reply(tab)

            self.browse_post(tab)

        finally:
            try:
                tab.close()
            except:
                pass

    def click_like(self, page):
        try:
            like_btn = page.ele(".discourse-reactions-reaction-button:not(.has-reacted)")
            if like_btn:
                like_btn.click(by_js=True)
                logger.success("点赞成功")
                time.sleep(random.uniform(0.8, 1.8))
            else:
                logger.info("该帖可能已点赞或无点赞按钮")
        except Exception as e:
            logger.debug(f"点赞操作异常: {e}")

    def auto_reply(self, page):
        try:
            editor = (
                page.ele(".reply-input-container .d-editor-input") or
                page.ele(".composer .d-editor-input") or
                page.ele("css:.composer-textarea")
            )
            if not editor:
                logger.info("未找到回复编辑器，跳过自动回复")
                return

            avail = [r for r in REPLY_POOL if r not in self.used_replies]
            if not avail:
                avail = REPLY_POOL[:]
                self.used_replies.clear()

            text = random.choice(avail)
            self.used_replies.add(text)

            logger.info(f"准备回复: {text}")

            editor.input(text)
            time.sleep(random.uniform(1.2, 2.4))

            send_btn = (
                page.ele(".composer .btn-primary") or
                page.ele("css:button[title*='回复']") or
                page.ele("text=回复")
            )

            if send_btn:
                send_btn.click(by_js=True)
                logger.success(f"回复成功 → {text}")
                time.sleep(random.uniform(3, 6))
            else:
                logger.warning("未找到发送按钮")

        except Exception as e:
            logger.error(f"自动回复失败: {e}")

    def browse_post(self, page):
        for _ in range(random.randint(6, 12)):
            scroll_px = random.randint(480, 720)
            page.run_js(f"window.scrollBy(0, {scroll_px})")
            time.sleep(random.uniform(1.8, 4.2))

            if random.random() < 0.04:
                logger.info("随机提前结束本帖浏览")
                break

            at_bottom = page.run_js(
                "return window.scrollY + window.innerHeight + 200 >= document.body.scrollHeight"
            )
            if at_bottom:
                logger.info("已滚动到底部")
                break

    def print_connect_info(self):
        try:
            r = self.session.get("https://connect.linux.do/", impersonate="chrome")
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.select("table tr")
            data = []
            for row in rows[1:]:
                cols = row.select("td")
                if len(cols) >= 3:
                    data.append([
                        cols[0].get_text(strip=True),
                        cols[1].get_text(strip=True) or "0",
                        cols[2].get_text(strip=True) or "?"
                    ])
            if data:
                print("\n" + "="*40)
                print("Linux.do Connect 信息")
                print(tabulate(data, headers=["项目", "当前", "要求"], tablefmt="github"))
                print("="*40 + "\n")
        except Exception as e:
            logger.warning(f"获取 connect 信息失败: {e}")

    def send_notifications(self, success=True):
        emoji = "✅" if success else "⚠️"
        msg = f"{emoji} Linux.do 签到 {'成功' if success else '部分完成'} | 用户: {USERNAME}"
        if BROWSE_ENABLED:
            msg += " + 浏览/互动任务执行"

        # Gotify
        if GOTIFY_URL and GOTIFY_TOKEN:
            try:
                requests.post(
                    f"{GOTIFY_URL}/message?token={GOTIFY_TOKEN}",
                    json={"title": "Linux.do 签到", "message": msg, "priority": 4},
                    timeout=10
                )
                logger.success("Gotify 推送成功")
            except Exception as e:
                logger.error(f"Gotify 推送失败: {e}")

        # Server酱³
        if SC3_PUSH_KEY:
            match = re.match(r"sct(\d+)t", SC3_PUSH_KEY, re.I)
            if match:
                uid = match.group(1)
                url = f"https://{uid}.push.ft07.com/send/{SC3_PUSH_KEY}"
                try:
                    requests.get(url, params={"title": "Linux.do", "desp": msg}, timeout=10)
                    logger.success("Server酱³ 推送成功")
                except Exception as e:
                    logger.error(f"Server酱³ 推送失败: {e}")
            else:
                logger.warning("SC3_PUSH_KEY 格式不正确")

        # WxPusher
        if WXPUSHER_APP_TOKEN and WXPUSHER_TOPIC_IDS:
            try:
                payload = {
                    "appToken": WXPUSHER_APP_TOKEN,
                    "content": msg,
                    "contentType": 1,
                    "topicIds": WXPUSHER_TOPIC_IDS,
                    "summary": "Linux.do 签到通知",
                }
                r = requests.post(
                    "https://wxpusher.zjiecode.com/api/send/message",
                    json=payload, timeout=12
                )
                if r.json().get("code") == 1000:
                    logger.success("WxPusher 推送成功")
                else:
                    logger.error(f"WxPusher 返回错误: {r.text}")
            except Exception as e:
                logger.error(f"WxPusher 推送异常: {e}")

        # Telegram
        if TELEGRAM_TOKEN and TELEGRAM_USERID:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                params = {
                    "chat_id": TELEGRAM_USERID,
                    "text": msg,
                    "disable_web_page_preview": True,
                }
                r = requests.get(url, params=params, timeout=10)
                if r.json().get("ok"):
                    logger.success("Telegram 推送成功")
                else:
                    logger.error(f"Telegram 失败: {r.text}")
            except Exception as e:
                logger.error(f"Telegram 推送异常: {e}")

    def run(self):
        success = False
        try:
            if not USERNAME or not PASSWORD:
                logger.error("缺少用户名或密码")
                return

            if self.login():
                if BROWSE_ENABLED:
                    self.click_topic()
                success = True
            else:
                logger.error("登录失败，无法继续")

            self.send_notifications(success=success)

        except Exception as e:
            logger.exception(f"主流程异常: {e}")
            self.send_notifications(success=False)
        finally:
            try:
                self.page.close()
            except:
                pass
            try:
                self.browser.quit()
            except:
                pass


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("缺少必要的环境变量：请设置 USERNAME / PASSWORD")
        sys.exit(1)

    bot = LinuxDoBrowser()
    bot.run()
