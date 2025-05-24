import os
import cloudscraper
import logging
from typing import Optional
import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# 环境变量配置
ENV_CONFIG = {
    "required": {
        "FC_USERNAME": os.getenv("FC_USERNAME"),
        "FC_PASSWORD": os.getenv("FC_PASSWORD"),
        "FC_MACHINE_ID": os.getenv("FC_MACHINE_ID")
    },
    "optional": {
        "TG_BOT_TOKEN": os.getenv("TG_BOT_TOKEN"),
        "TG_CHAT_ID": os.getenv("TG_CHAT_ID"),
        "FC_RENEW_MONTH": os.getenv("FC_RENEW_MONTH", "1")  # 默认续费1个月
    }
}

# 环境变量校验
if not all(ENV_CONFIG["required"].values()):
    missing = [k for k, v in ENV_CONFIG["required"].items() if not v]
    logging.error(f"缺少必要环境变量: {', '.join(missing)}")
    exit(1)

# 网站配置
URL_CONFIG = {
    "login": "https://freecloud.ltd/login",
    "console": "https://freecloud.ltd/member/index",
    "renew": f"https://freecloud.ltd/server/detail/{ENV_CONFIG['required']['FC_MACHINE_ID']}/renew"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": URL_CONFIG["login"],
    "Origin": "https://freecloud.ltd"
}

def send_telegram(message: str) -> None:
    """发送Telegram通知"""
    if not ENV_CONFIG["optional"]["TG_BOT_TOKEN"] or not ENV_CONFIG["optional"]["TG_CHAT_ID"]:
        return

    try:
        url = f"https://api.telegram.org/bot{ENV_CONFIG['optional']['TG_BOT_TOKEN']}/sendMessage"
        payload = {
            "chat_id": ENV_CONFIG["optional"]["TG_CHAT_ID"],
            "text": f"FreeCloud续费通知\n{message}",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.warning(f"Telegram通知发送失败: {str(e)}")

def create_session() -> Optional[cloudscraper.CloudScraper]:
    """创建绕过Cloudflare的会话"""
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False
        }
    )

def login(scraper: cloudscraper.CloudScraper) -> bool:
    """执行登录流程"""
    logging.info("⏳ 正在登录FreeCloud...")
    
    try:
        # 获取CSRF令牌
        login_page = scraper.get(URL_CONFIG["login"], timeout=15)
        soup = BeautifulSoup(login_page.text, "html.parser")
        csrf_token = soup.find("input", {"name": "_token"})["value"]
        
        # 构造登录数据
        login_data = {
            "_token": csrf_token,
            "username": ENV_CONFIG["required"]["FC_USERNAME"],
            "password": ENV_CONFIG["required"]["FC_PASSWORD"],
            "submit": "1"
        }

        # 提交登录
        resp = scraper.post(
            URL_CONFIG["login"],
            data=login_data,
            headers=HEADERS,
            allow_redirects=True,
            timeout=20
        )

        # 验证登录状态
        if "freecloud_session" not in scraper.cookies.get_dict():
            logging.error("❌ 登录失败：未找到会话Cookie")
            send_telegram("❌ 登录失败：凭证错误或验证失败")
            return False
            
        logging.info("✅ 登录成功")
        send_telegram("🔑 登录成功")
        return True

    except Exception as e:
        logging.error(f"登录异常: {str(e)}")
        send_telegram(f"⚠️ 登录异常: {str(e)}")
        return False

def renew_service(scraper: cloudscraper.CloudScraper) -> None:
    """执行续费操作"""
    logging.info(f"🔄 正在续费服务器 {ENV_CONFIG['required']['FC_MACHINE_ID']}")
    
    try:
        # 获取续费页面获取CSRF
        renew_page = scraper.get(URL_CONFIG["renew"], timeout=15)
        soup = BeautifulSoup(renew_page.text, "html.parser")
        csrf_token = soup.find("input", {"name": "_token"})["value"]

        # 构造续费数据
        renew_data = {
            "_token": csrf_token,
            "month": ENV_CONFIG["optional"]["FC_RENEW_MONTH"],
            "submit": "1",
            "coupon_id": 0
        }

        # 提交续费
        resp = scraper.post(
            URL_CONFIG["renew"],
            data=renew_data,
            headers=HEADERS,
            timeout=20
        )
        resp.raise_for_status()

        # 解析响应
        result = resp.json()
        msg = result.get("msg", "未知响应")
        logging.info(f"续费结果: {msg}")
        send_telegram(f"🔄 续费结果: {msg}")

    except Exception as e:
        logging.error(f"续费失败: {str(e)}")
        send_telegram(f"❌ 续费失败: {str(e)}")

if __name__ == "__main__":
    # 初始化会话
    scraper = create_session()
    if not scraper:
        logging.error("无法创建会话")
        exit(1)

    # 执行登录
    if login(scraper):
        renew_service(scraper)
    else:
        logging.error("流程终止")
