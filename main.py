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
        # 现代 Chrome 136 UA + headers（Discourse 敏感）
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

        # 先访问首页预热 cookie（Discourse 常需先拿 cookie）
        logger.info("预热首页 cookie...")
        try:
            self.session.get(HOME_URL, impersonate="chrome136", timeout=15)
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.warning(f"首页预热失败（不影响）: {e}")

        # 获取 CSRF Token
        logger.info("获取 CSRF token...")
        try:
            # 优先用 chrome136（2026 最新支持）
            resp_csrf = self.session.get(CSRF_URL, impersonate="chrome136")
            resp_csrf.raise_for_status()
            csrf_data = resp_csrf.json()
            csrf_token = csrf_data.get("csrf")
            if not csrf_token:
                logger.error("CSRF token 为空")
                return False
            logger.info(f"CSRF Token obtained: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取 CSRF 失败: {str(e)}")
            # Fallback 1: 尝试 chrome131
            try:
                resp_csrf = self.session.get(CSRF_URL, impersonate="chrome131")
                csrf_token = resp_csrf.json().get("csrf")
                logger.info("Fallback chrome131 CSRF 成功")
            except:
                # Fallback 2: 无 impersonate + 更宽松 headers
                try:
                    resp_csrf = self.session.get(CSRF_URL)
                    csrf_token = resp_csrf.json().get("csrf")
                    logger.info("Fallback 无 impersonate CSRF 成功")
                except Exception as fallback_e:
                    logger.error(f"所有 CSRF fallback 失败: {str(fallback_e)}")
                    return False

        # 登录
        logger.info("正在登录...")
        login_headers = self.session.headers.copy()
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
        self.page.get(HOME_URL)
        time.sleep(random.uniform(5, 8))  # 多等一点，页面加载

        # 验证
        try:
            if self.page.ele("@id=current-user", timeout=10) or "avatar" in self.page.html.lower():
                logger.info("登录验证成功")
                return True
            else:
                logger.error("未找到登录标志")
                return False
        except Exception as e:
            logger.error(f"登录验证异常: {e}")
            return False

    # 其余方法保持不变（click_topic, auto_reply 等），只调整 print_connect_info
    def print_connect_info(self):
        logger.info("获取连接信息")
        try:
            resp = self.session.get("https://connect.linux.do/", impersonate="chrome136")
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
            if info:
                print("--------------Connect Info-----------------")
                print(tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
        except Exception as e:
            logger.warning(f"Connect Info 获取失败: {e}")

    # send_notifications 等其他方法保持不变

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

            self.send_notifications(success)
        except Exception as e:
            logger.exception(f"主流程异常: {e}")
            self.send_notifications(False)
        finally:
            try:
                self.page.close()
            except:
                pass
            try:
                self.browser.quit()
            except:
                pass

    # ... (click_topic, click_one_topic, auto_reply, browse_post, click_like, send_notifications 方法保持原样)

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("请设置 USERNAME 和 PASSWORD")
        sys.exit(1)
    l = LinuxDoBrowser()
    l.run()
