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
                        logger.info(f"将在 {sleep_s:.2f}s 后重试")
                        time.sleep(sleep_s)
            return None
        return wrapper
    return decorator

os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

USERNAME = os.environ.get("LINUXDO_USERNAME") or os.environ.get("USERNAME")
PASSWORD = os.environ.get("LINUXDO_PASSWORD") or os.environ.get("PASSWORD")
BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in ["false", "0", "off"]

GOTIFY_URL = os.environ.get("GOTIFY_URL")
GOTIFY_TOKEN = os.environ.get("GOTIFY_TOKEN")
SC3_PUSH_KEY = os.environ.get("SC3_PUSH_KEY")
WXPUSHER_APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN")
WXPUSHER_TOPIC_IDS_STR = os.environ.get("WXPUSHER_TOPIC_IDS", "")
WXPUSHER_TOPIC_IDS = [int(tid.strip()) for tid in WXPUSHER_TOPIC_IDS_STR.split(",") if tid.strip().isdigit()] if WXPUSHER_TOPIC_IDS_STR else []
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_USERID = os.environ.get("TELEGRAM_USERID")

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"

REPLY_POOL = [
    "感谢分享！学到了", "非常有帮助的帖子，收藏了", "思路很清晰，mark一下",
    "正好最近也在研究这个，谢谢楼主", "+1 期待后续更新", "干货满满，受教了",
    "这个方法不错，试试看", "楼主牛啊，膜拜", "简单易懂，适合新手",
    "已阅，感谢大佬", "顶一下，支持原创", "学习了，谢谢分享经验",
    "这个坑我也踩过，解法很实用", "mark，回头仔细看", "内容质量很高，建议置顶",
]

class LinuxDoBrowser:
    def __init__(self):
        from sys import platform
        ua_platform = "X11; Linux x86_64" if platform in ("linux", "linux2") else \
                      "Macintosh; Intel Mac OS X 10_15_7" if platform == "darwin" else \
                      "Windows NT 10.0; Win64; x64" if platform == "win32" else "X11; Linux x86_64"

        co = ChromiumOptions().headless(True).incognito(True)\
             .set_argument("--no-sandbox").set_argument("--disable-dev-shm-usage")
        co.set_user_agent(f"Mozilla/5.0 ({ua_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")

        self.browser = Chromium(co)
        self.page = self.browser.new_tab()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": HOME_URL,
            "Sec-Ch-Ua": '"Chromium";v="136", "Not)A;Brand";v="99", "Google Chrome";v="136"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        })

        self.used_replies = set()

    def login(self):
        logger.info("开始登录 Linux.do")

        logger.info("预热首页 cookie...")
        try:
            self.session.get(HOME_URL, impersonate="chrome136", timeout=15)
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.warning(f"首页预热失败（不影响）: {e}")

        logger.info("获取 CSRF token...")
        try:
            resp_csrf = self.session.get(CSRF_URL, impersonate="chrome136")
            resp_csrf.raise_for_status()
            csrf_token = resp_csrf.json().get("csrf")
            if not csrf_token:
                logger.error("CSRF token 为空")
                return False
            logger.info(f"CSRF Token obtained: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取 CSRF 失败: {str(e)}")
            return False

        logger.info("正在登录...")
        login_headers = self.session.headers.copy()
        login_headers.update({
            "X-CSRF-Token": csrf_token,
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
            resp_login = self.session.post(SESSION_URL, data=data, impersonate="chrome136", headers=login_headers)
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

        logger.info("同步 Cookie 到 DrissionPage...")
        dp_cookies = [{"name": k, "value": v, "domain": ".linux.do", "path": "/"} for k, v in self.session.cookies.get_dict().items()]
        self.page.set.cookies(dp_cookies)
        self.page.get(HOME_URL)
        time.sleep(random.uniform(5, 8))

        try:
            if self.page.ele("@id=current-user", timeout=10) or "avatar" in self.page.html.lower():
                logger.info("登录验证成功")
                return True
            logger.error("未找到登录标志")
            return False
        except Exception as e:
            logger.error(f"登录验证异常: {e}")
            return False

    def click_topic(self):
        if not BROWSE_ENABLED:
            logger.info("浏览任务已关闭，跳过")
            return True
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
            if not topic_list:
                logger.warning("未找到主题帖")
                return False
            logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择{min(10, len(topic_list))}个")
            for topic in random.sample(topic_list, min(10, len(topic_list))):
                href = topic.attr("href")
                if href:
                    full_url = HOME_URL.rstrip('/') + href if href.startswith('/') else href
                    self.click_one_topic(full_url)
            return True
        except Exception as e:
            logger.error(f"点击主题列表失败: {e}")
            return False

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
            except:
                pass

    def click_like(self, page):
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                like_button.click()
                logger.success("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已点赞")
        except Exception as e:
            logger.error(f"点赞失败: {str(e)}")

    def auto_reply(self, page):
        try:
            reply_box = page.ele(".d-editor-input") or page.ele("css:.composer .d-editor-input")
            if not reply_box:
                logger.info("未找到回复框，跳过")
                return
            avail = [r for r in REPLY_POOL if r not in self.used_replies] or REPLY_POOL[:]
            self.used_replies.clear() if not avail else None
            text = random.choice(avail)
            self.used_replies.add(text)
            reply_box.input(text)
            time.sleep(random.uniform(0.8, 1.6))
            send_btn = page.ele(".btn-primary") or page.ele("text=回复")
            if send_btn:
                send_btn.click()
                logger.success(f"回复成功: {text}")
                time.sleep(random.uniform(2.5, 4.5))
            else:
                logger.warning("未找到发送按钮")
        except Exception as e:
            logger.error(f"自动回复失败: {str(e)}")

    def browse_post(self, page):
        for _ in range(8):
            page.run_js(f"window.scrollBy(0, {random.randint(500, 700)})")
            time.sleep(random.uniform(2, 5))
            if random.random() < 0.05:
                break
            if page.run_js("return window.scrollY + window.innerHeight >= document.body.scrollHeight - 200"):
                break

    def print_connect_info(self):
        logger.info("获取连接信息")
        try:
            resp = self.session.get("https://connect.linux.do/", impersonate="chrome136")
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            info = [[c[0].text.strip(), c[1].text.strip() or "0", c[2].text.strip() or "0"] for row in rows[1:] if len(c := row.select("td")) >= 3]
            if info:
                print("--------------Connect Info-----------------")
                print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.warning(f"Connect Info 失败: {e}")

    def send_notifications(self, success=True):
        emoji = "✅" if success else "⚠️"
        msg = f"{emoji} Linux.do 签到 {'成功' if success else '失败/部分完成'} | 用户: {USERNAME}"
        if BROWSE_ENABLED and success:
            msg += " + 浏览任务完成"

        if GOTIFY_URL and GOTIFY_TOKEN:
            try:
                requests.post(f"{GOTIFY_URL}/message?token={GOTIFY_TOKEN}", json={"title": "Linux.do", "message": msg}, timeout=10)
                logger.success("Gotify 推送成功")
            except Exception as e:
                logger.error(f"Gotify 失败: {e}")

        if SC3_PUSH_KEY:
            match = re.match(r"sct(\d+)t", SC3_PUSH_KEY, re.I)
            if match:
                uid = match.group(1)
                url = f"https://{uid}.push.ft07.com/send/{SC3_PUSH_KEY}"
                try:
                    requests.get(url, params={"title": "Linux.do", "desp": msg}, timeout=10)
                    logger.success("Server酱³ 推送成功")
                except Exception as e:
                    logger.error(f"Server酱³ 失败: {e}")

        if WXPUSHER_APP_TOKEN and WXPUSHER_TOPIC_IDS:
            try:
                payload = {"appToken": WXPUSHER_APP_TOKEN, "content": msg, "contentType": 1, "topicIds": WXPUSHER_TOPIC_IDS}
                r = requests.post("https://wxpusher.zjiecode.com/api/send/message", json=payload, timeout=10)
                if r.json().get("code") == 1000:
                    logger.success("WxPusher 推送成功")
            except Exception as e:
                logger.error(f"WxPusher 失败: {e}")

        if TELEGRAM_TOKEN and TELEGRAM_USERID:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                params = {"chat_id": TELEGRAM_USERID, "text": msg, "parse_mode": "HTML"}
                r = requests.get(url, params=params, timeout=10)
                if r.json().get("ok"):
                    logger.success("Telegram 推送成功")
            except Exception as e:
                logger.error(f"Telegram 失败: {e}")

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
            self.send_notifications(success)
        except Exception as e:
            logger.exception(f"主流程异常: {e}")
            self.send_notifications(False)
        finally:
            try:
                self.page.close()
                self.browser.quit()
            except:
                pass

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("请设置 USERNAME 和 PASSWORD")
        sys.exit(1)
    l = LinuxDoBrowser()
    l.run()
