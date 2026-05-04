# -*- coding: utf-8 -*-
"""
本地手动测试微信公众号模板消息推送
用法：
    cd daily_stock_analysis
    python scripts/test_wechat_mp.py

需要先 export 以下环境变量（或写入 .env）：
    WECHAT_MP_APPID
    WECHAT_MP_SECRET
    WECHAT_MP_TEMPLATE_ID
    WECHAT_MP_USER_OPENID
可选：
    WECHAT_MP_CITY_ID         默认 45.5017,-73.5673
    WECHAT_MP_TIMEZONE        默认 America/Montreal
    WECHAT_MP_DESTINATION_TEXT
"""
import logging
import sys
from pathlib import Path

# 让脚本无需安装就能 import src.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from src.config import get_config
from src.notification_sender import WechatMpSender

FAKE_REPORT = """## 今日A股报告
今日A股市场整体呈现小幅下跌态势。
- 上证指数: 4093.25 (↓0.32%)
- 深证成指: 15043.45 (↓0.88%)
- 创业板指: 3720.25 (↓0.87%)
- 科创50: 1432.59 (↓1.28%)
- 领涨: 食用菌、风力发电、油气及炼化工程
- 领跌: 稀土、白银、钼
"""


def main() -> int:
    import os
    import requests as _requests

    cfg = get_config()
    sender = WechatMpSender(cfg)

    test_openid = os.getenv("WECHAT_MP_TEST_OPENID")
    if test_openid:
        sender._wechat_mp_user_openid = test_openid
        print(f"[test] override openid -> {test_openid}")

    token = sender._get_access_token()
    if not token:
        print("failed to get token")
        return 1

    weather = sender._get_weather()
    commentary = sender._get_commentary(weather['code'])
    remarks = sender._split_by_width(commentary, 38, 3)
    dests = sender._split_by_width(sender._wechat_mp_destination_text, 38, 2)

    # 纯 ASCII 诊断：确认 joke1-8 变量名都能被模板正确渲染
    HARDCODED_JOKES = [
        "LINE1 hello world",
        "LINE2 hello world",
        "LINE3 hello world",
        "LINE4 hello world",
        "LINE5 hello world",
        "LINE6 hello world",
        "LINE7 hello world",
        "LINE8 hello world",
    ]

    def _clean(t):
        return ' '.join((t or '').split()) or '-'

    data = {
        "date":    {"value": _clean(sender._get_local_time()),                                               "color": "#173177"},
        "weather": {"value": _clean(f"{weather['name']}, {weather['temp']} (feels {weather['feels_like']})"), "color": "#FF6347"},
    }
    for i, v in enumerate(remarks, 1):
        data[f"remark{i}"] = {"value": _clean(v), "color": "#5B8DB8"}
    for i, v in enumerate(dests, 1):
        data[f"destination{i}"] = {"value": _clean(v), "color": "#888888"}
    for i, v in enumerate(HARDCODED_JOKES, 1):
        data[f"joke{i}"] = {"value": _clean(v), "color": "#2E7D32"}

    print("字段长度:", {k: len(v['value']) for k, v in data.items()})

    message = {
        "touser": sender._wechat_mp_user_openid,
        "template_id": sender._wechat_mp_template_id,
        "url": "https://mp.weixin.qq.com",
        "topcolor": "#FF0000",
        "data": data,
    }
    url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}"
    resp = _requests.post(url, json=message, timeout=10).json()
    print("响应:", resp)
    return 0 if resp.get('errcode') == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
