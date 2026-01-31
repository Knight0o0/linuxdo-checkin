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
    "支持一下，感谢付出",
    "这个思路很赞！",
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
            f"Mozilla/5.0 ({ua_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )

        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        self.used_replies = set()

    def login(self):
        logger.info("开始登录 Linux.do")

        # 获取 CSRF Token
        logger.info("获取 CSRF token...")
        headers = {
            "User-Agent": self.session.headers["User-Agent"],
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        try:
            resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="chrome136")
            resp_csrf.raise_for_status()
            csrf_data = resp_csrf.json()
            csrf_token = csrf_data.get("csrf")
            if not csrf_token:
                logger.error("未能获取 CSRF token")
                return False
            logger.info(f"CSRF Token obtained: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取 CSRF 失败: {str(e)}")
            # Fallback: 尝试无 impersonate
            try:
                resp_csrf = self.session.get(CSRF_URL, headers=headers)
                csrf_token = resp_csrf.json().get("csrf")
                logger.info("Fallback CSRF 成功")
            except Exception as fallback_e:
                logger.error(f"Fallback CSRF 也失败: {str(fallback_e)}")
                return False

        # 登录
        logger.info("正在登录...")
        login_headers = headers.copy()
        login_headers.update(
            {
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://linux.do",
            }
        )
        data = {
            "login": USERNAME,
            "password": PASSWORD,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }
        try:
            resp_login = self.session.post(
                SESSION_URL, data=data, impersonate="chrome136", headers=login_headers
            )
            resp_login.raise_for_status()
            response_json = resp_login.json()
            if response_json.get("error"):
                logger.error(f"登录失败: {response_json.get('error')}")
                return False
            logger.info("登录成功!")
        except Exception as e:
            logger.error(f"登录请求异常: {e}")
            return False

        self.print_connect_info() 

        # 同步 Cookie 到 DrissionPage
        logger.info("同步 Cookie 到 DrissionPage...")
        cookies_dict = self.session.cookies.get_dict()
        dp_cookies = []
        for name, value in cookies_dict.items():
            dp_cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": ".linux.do",
                    "path": "/",
                }
            )
        self.page.set.cookies(dp_cookies)
        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)
        time.sleep(5)

        try:
            user_ele = self.page.ele("@id=current-user")
        except Exception as e:
            logger.warning(f"登录验证失败: {str(e)}")
            return True

        if not user_ele:
            if "avatar" in self.page.html:
                logger.info("登录验证成功 (通过 avatar)")
                return True
            logger.error("登录验证失败 (未找到 current-user)")
            return False
        else:
            logger.info("登录验证成功")
            return True

    def click_topic(self):
        topic_list = self.page.ele("@id=list-area").eles(".:title")
        if not topic_list:
            logger.error("未找到主题帖")
            return False
        logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择10个")
        for topic in random.sample(topic_list, min(10, len(topic_list))):
            self.click_one_topic(topic.attr("href"))
        return True

    @retry_decorator()
    def click_one_topic(self, topic_url):
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            time.sleep(random.uniform(1.2, 2.8))

            if random.random() < 0.3:
                self.click_like(new_page)

            if random.random() < 0.08:
                self.auto_reply(new_page)

            self.browse_post(new_page)
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def auto_reply(self, page):
        try:
            reply_box = page.ele(".reply-input-container .d-editor-input") or page.ele("css:.composer .d-editor-input")
            if not reply_box:
                logger.info("未找到回复输入框，跳过自动回复")
                return

            available_replies = [r for r in REPLY_POOL if r not in self.used_replies]
            if not available_replies:
                available_replies = REPLY_POOL[:]
                self.used_replies.clear()

            reply_text = random.choice(available_replies)
            self.used_replies.add(reply_text)

            logger.info(f"准备自动回复：{reply_text}")

            reply_box.input(reply_text)
            time.sleep(random.uniform(0.8, 1.6))

            send_btn = page.ele(".composer .btn-primary") or page.ele("text=回复") or page.ele("css:.reply-btn")
            if send_btn:
                send_btn.click()
                logger.success(f"自动回复成功：{reply_text}")
                time.sleep(random.uniform(2.5, 4.5))
            else:
                logger.warning("未找到回复发送按钮，回复失败")

        except Exception as e:
            logger.error(f"自动回复失败: {str(e)}")

    def browse_post(self, page):
        prev_url = None
        for _ in range(10):
            scroll_distance = random.randint(550, 650)
            logger.info(f"向下滚动 {scroll_distance} 像素...")
            page.run_js(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"已加载页面: {page.url}")

            if random.random() < 0.03:
                logger.success("随机退出浏览")
                break

            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success("已到达页面底部，退出浏览")
                break

            wait_time = random.uniform(2, 4)
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        try:
            login_res = self.login()
            if not login_res:
                logger.warning("登录验证失败")

            if BROWSE_ENABLED:
                click_topic_res = self.click_topic()
                if not click_topic_res:
                    logger.error("点击主题失败，程序终止")
                    return
                logger.info("完成浏览任务")

            self.send_notifications(BROWSE_ENABLED)
        finally:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.browser.quit()
            except Exception:
                pass

    def click_like(self, page):
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def print_connect_info(self):
        logger.info("获取连接信息")
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://linux.do/",
        }
        try:
            resp = self.session.get(
                "https://connect.linux.do/", headers=headers, impersonate="chrome136"
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            info = []
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 3:
                    project = cells[0].text.strip()
                    current = cells[1].text.strip() or "0"
                    requirement = cells[2].text.strip() or "0"
                    info.append([project, current, requirement])
            print("--------------Connect Info-----------------")
            print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.error(f"获取连接信息失败: {str(e)}")

    def send_notifications(self, browse_enabled):
        status_msg = f"✅每日登录成功: {USERNAME}"
        if browse_enabled:
            status_msg += " + 浏览任务完成"

        if GOTIFY_URL and GOTIFY_TOKEN:
            try:
                response = requests.post(
                    f"{GOTIFY_URL}/message",
                    params={"token": GOTIFY_TOKEN},
                    json={"title": "LINUX DO", "message": status_msg, "priority": 1},
                    timeout=10,
                )
                response.raise_for_status()
                logger.success("消息已推送至Gotify")
            except Exception as e:
                logger.error(f"Gotify推送失败: {str(e)}")
        else:
            logger.info("未配置Gotify环境变量，跳过通知发送")

        if SC3_PUSH_KEY:
            match = re.match(r"sct(\d+)t", SC3_PUSH_KEY, re.I)
            if not match:
                logger.error("❌ SC3_PUSH_KEY格式错误，无法使用Server酱³推送")
                return
            uid = match.group(1)
            url = f"https://{uid}.push.ft07.com/send/{SC3_PUSH_KEY}"
            params = {"title": "LINUX DO", "desp": status_msg}
            attempts = 5
            for attempt in range(attempts):
                try:
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    logger.success(f"Server酱³推送成功: {response.text}")
                    break
                except Exception as e:
                    logger.error(f"Server酱³推送失败: {str(e)}")
                    if attempt < attempts - 1:
                        sleep_time = random.randint(180, 360)
                        logger.info(f"将在 {sleep_time} 秒后重试...")
                        time.sleep(sleep_time)

        if WXPUSHER_APP_TOKEN and WXPUSHER_TOPIC_IDS:
            try:
                payload = {
                    "appToken": WXPUSHER_APP_TOKEN,
                    "content": status_msg,
                    "contentType": 1,
                    "topicIds": WXPUSHER_TOPIC_IDS,
                    "summary": "Linux.do 签到通知",
                }
                resp = requests.post(
                    "https://wxpusher.zjiecode.com/api/send/message",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") == 1000:
                    logger.success("WxPusher 推送成功")
                else:
                    logger.error(f"WxPusher 推送失败: {result}")
            except Exception as e:
                logger.error(f"WxPusher 推送异常: {str(e)}")
        else:
            logger.info("未配置 WXPUSHER_APP_TOKEN 或 WXPUSHER_TOPIC_IDS，跳过 WxPusher 通知")

        if TELEGRAM_TOKEN and TELEGRAM_USERID:
            try:
                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                params = {
                    "chat_id": TELEGRAM_USERID,
                    "text": status_msg,
                    "parse_mode": "HTML",
                }
                resp = requests.get(telegram_url, params=params, timeout=10)
                resp.raise_for_status()
                result = resp.json()
                if result.get("ok"):
                    logger.success("Telegram 推送成功")
                else:
                    logger.error(f"Telegram 推送失败: {result.get('description')}")
            except Exception as e:
                logger.error(f"Telegram 推送异常: {str(e)}")
        else:
            logger.info("未配置 TELEGRAM_TOKEN 或 TELEGRAM_USERID，跳过 Telegram 通知")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("请设置 USERNAME 和 PASSWORD")
        exit(1)
    l = LinuxDoBrowser()
    l.run()
