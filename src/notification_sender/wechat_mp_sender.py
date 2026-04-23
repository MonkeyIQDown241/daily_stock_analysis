# -*- coding: utf-8 -*-
"""
微信公众号模板消息发送服务（多字段模板）

模板格式（在公众号后台新建）:
    It's {{date.DATA}}
    It's {{weather.DATA}} {{remark.DATA}}
    {{destination.DATA}}
    Murphy, today's briefing:
    ✦ {{joke1.DATA}}
    📈 {{joke2.DATA}}

字段映射:
    date        -> 当地时间
    weather     -> 天气描述 + 温度（含体感）
    remark      -> 风速 + 湿度
    destination -> 倒计时（默认 Error 404 文案，可通过 WECHAT_MP_DESTINATION_TEXT 覆盖）
    joke1       -> 根据天气随机选评语（hydration / photosynthesis / mood / lucky_color）
    joke2       -> 当日股票分析摘要（由调用方传入 content）
"""
import logging
import random
import time
from datetime import datetime
from typing import Optional

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from src.config import Config

logger = logging.getLogger(__name__)


# ---------- 评语库 ----------
_COMMENTARY = {
    'hydration': [
        "Hydration Risk: 25%. Brain coolant levels are low. Please refill with H2O.",
        "System Fluidity: Optimal. Keep going with a glass of warm tea; steam is good for the soul.",
        "Metabolic Alert: Dry air detected. Recommend 300ml of water to maintain system elasticity.",
        "Hydration Sync: 15% deficit. A glass of water now is a high-priority patch for your energy.",
        "Daily Intake Goal: 2.0L. Think of it as mandatory maintenance for your internal hardware.",
        "Electrolyte Balance: 92%. A pinch of salt or a piece of fruit will boost conductivity.",
        "Humidity Compensation: Ambient air is dry. Protect your vocal cords — drink up.",
        "Circulatory Efficiency: Rising. Support it with a 250ml glass of room-temperature water.",
        "Fluid Retention Check: Low. Good time to flush the system with clean, filtered water.",
        "Refreshment Logic: Water isn't just fuel — it's a reset button for your focus. Take a sip.",
    ],
    'photosynthesis': [
        "Photosynthesis Requirement: 10 mins. UV rays are charging your battery today.",
        "Vitamin D Sync: Missing. Suggest 15 mins of natural light to stabilize your mood.",
        "Atmospheric Pressure: Stable. Perfect time to reset your focal point at the horizon.",
        "Sky Quality: 85% Soft. Diffused light today is nature's 'beauty filter.' Enjoy it.",
        "Wind Speed Effect: Refreshing. A 5-min walk clears the temporary cache in your mind.",
        "Cloud Cover: High. Perfect lighting for deep focus — no glare, just muted productivity.",
        "Light Intensity: Subdued. A warm lamp indoors can mimic the missing sun.",
        "Air Quality: Crisp. Three deep breaths near an open window will oxygenate the system.",
        "Solar Opportunity: A 5-min sun-break today provides a 24-hour mood dividend.",
        "Shadow Analysis: Soft and blurred. The world is in 'gentle mode' today. Slow down.",
        "Natural Frequency: Low and steady. Sync your pace with the quiet air outside.",
        "Horizon Scan: Suggested. Looking far away reduces digital eye strain today.",
    ],
    'mood': [
        "Mood Resistance: Strong Support. Your foundation is solid despite external volatility.",
        "Market Sentiment: Bullish on peace. High probability of unexpected joy today.",
        "Emotional Inflation: 0%. Today is a high-purchasing-power day for kindness.",
        "Vibe Check: Low Latency. Responses sharp, spirits steady — proceed with high-value tasks.",
        "Stress Volatility: Decreasing. Fear & Greed index is neutral. It's a good day to just *be*.",
        "Psychological Buffer: +20%. You have extra capacity today. Trust the backup.",
        "Market Outlook: Steady growth. Focus on small, incremental personal improvements.",
        "Asset Allocation: High priority on 'Self-Care.' It's the only investment with a guaranteed ROI.",
        "Volatility Protection: Activated. You have the inner resilience to absorb any short-term noise.",
        "Sentiment: Turning optimistic. The fundamentals of your day are stronger than they appear.",
        "Trading Volume: Low. A quiet day is a luxury — use it to consolidate and rest.",
        "Diversification: Spread energy across work, rest, and play to maintain a balanced portfolio.",
    ],
    'lucky_color': [
        "Lucky Color: #F5F5DC (Oatmeal). A soft, neutral shade for a day that requires patience and calm.",
        "Lucky Color: #FFD700 (Sunset Gold). A reminder that even difficult endings can be beautiful.",
        "Lucky Color: #E6E6FA (Lavender). Best for reducing system noise and finding a moment of silence.",
        "Lucky Color: #2F4F4F (Dark Slate). Solid, grounded, and sophisticated — just like your core.",
        "Lucky Color: #F0FFF0 (Honeydew). A fresh start for a fresh morning. Clean the slate.",
        "Lucky Color: #87CEEB (Sky Blue). Keep your head up; the color of the sky is your limit today.",
        "Lucky Color: #A9A9A9 (Dark Gray). Elegant and steady, like a quiet city street before dawn.",
        "Lucky Color: #FFFDD0 (Cream). A soft, comforting light to navigate a busy schedule.",
        "Lucky Color: #98FB98 (Pale Green). Represents new growth and the quiet persistence of nature.",
        "Lucky Color: #708090 (Slate Blue). Calm and reflective — a thoughtful, balanced afternoon.",
        "Lucky Color: #FF7F50 (Coral). A spark of warmth to remind you of your own inner energy.",
        "Lucky Color: #B0C4DE (Light Steel Blue). Cool and professional, yet gentle on the eyes.",
    ],
}

_WEATHER_CATEGORY = {
    0: 'photosynthesis', 1: 'photosynthesis',
    2: 'mood', 3: 'mood',
    45: 'mood', 48: 'mood',
    51: 'hydration', 53: 'hydration', 55: 'hydration',
    61: 'hydration', 63: 'hydration', 65: 'hydration',
    71: 'lucky_color', 73: 'lucky_color', 75: 'lucky_color',
    95: 'mood',
}

_WEATHER_CODE_NAMES = {
    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing Rime Fog",
    51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Dense Drizzle",
    61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain",
    71: "Slight Snow", 73: "Moderate Snow", 75: "Heavy Snow",
    95: "Thunderstorm",
}

_DEFAULT_DESTINATION = (
    "Meeting Countdown: > Error 404:\n"
    "System is currently retrying... I'm working on a better version of the bridge."
)

# 单字段大致上限（公众号实测约 200 字符，留余量）
_FIELD_MAX_CHARS = 180
# Lucky Color 类强制概率（避免常年雨/晴时该类几乎不出现）
_LUCKY_COLOR_BIAS = 0.20


class WechatMpSender:

    def __init__(self, config: Config):
        self._wechat_mp_appid = getattr(config, 'wechat_mp_appid', None)
        self._wechat_mp_secret = getattr(config, 'wechat_mp_secret', None)
        self._wechat_mp_template_id = getattr(config, 'wechat_mp_template_id', None)
        self._wechat_mp_user_openid = getattr(config, 'wechat_mp_user_openid', None)
        self._wechat_mp_city_id = getattr(config, 'wechat_mp_city_id', '45.5017,-73.5673')
        self._wechat_mp_timezone = getattr(config, 'wechat_mp_timezone', 'America/Montreal')
        self._wechat_mp_destination_text = (
            getattr(config, 'wechat_mp_destination_text', None) or _DEFAULT_DESTINATION
        )
        self._wechat_mp_access_token: Optional[str] = None
        self._wechat_mp_token_expire_at: float = 0.0

    # ---------- access_token ----------
    def _get_access_token(self) -> Optional[str]:
        if self._wechat_mp_access_token and time.time() < self._wechat_mp_token_expire_at - 60:
            return self._wechat_mp_access_token
        try:
            url = (
                f"https://api.weixin.qq.com/cgi-bin/token"
                f"?grant_type=client_credential"
                f"&appid={self._wechat_mp_appid}&secret={self._wechat_mp_secret}"
            )
            resp = requests.get(url, timeout=10).json()
            token = resp.get('access_token')
            expires_in = resp.get('expires_in', 7200)
            if token:
                self._wechat_mp_access_token = token
                self._wechat_mp_token_expire_at = time.time() + expires_in
                return token
            logger.error("微信MP获取 access_token 失败: %s", resp)
        except Exception as e:
            logger.error("微信MP获取 access_token 异常: %s", e)
        return None

    # ---------- 天气 ----------
    def _get_weather(self) -> dict:
        try:
            lat, lon = self._wechat_mp_city_id.split(',')
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat.strip()}&longitude={lon.strip()}"
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m"
                f"&timezone={self._wechat_mp_timezone}"
            )
            current = requests.get(url, timeout=15).json()['current']
            code = current['weather_code']
            return {
                'code': code,
                'name': _WEATHER_CODE_NAMES.get(code, "Unknown"),
                'temp': f"{current['temperature_2m']}C",
                'feels_like': f"{current['apparent_temperature']}C",
                'wind': f"{current['wind_speed_10m']} km/h",
                'humidity': f"{current['relative_humidity_2m']}%",
            }
        except Exception as e:
            logger.warning("微信MP获取天气失败: %s", e)
            return {
                'code': -1, 'name': 'Unknown',
                'temp': '--', 'feels_like': '--', 'wind': '--', 'humidity': '--',
            }

    def _get_local_time(self) -> str:
        if ZoneInfo:
            try:
                now = datetime.now(ZoneInfo(self._wechat_mp_timezone))
                return now.strftime("%b %d, %Y %H:%M")
            except Exception:
                pass
        return datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")

    def _get_commentary(self, weather_code: int) -> str:
        if random.random() < _LUCKY_COLOR_BIAS:
            category = 'lucky_color'
        else:
            category = _WEATHER_CATEGORY.get(weather_code, 'lucky_color')
        return random.choice(_COMMENTARY[category])

    # ---------- 摘要清洗 ----------
    @staticmethod
    def _summarize(content: str, max_chars: int = _FIELD_MAX_CHARS) -> str:
        """从 markdown 报告里抽取一段紧凑摘要，截断到 max_chars 字符"""
        import re
        lines = []
        for raw in (content or '').splitlines():
            s = raw.strip()
            if not s:
                continue
            if s.startswith('#') or s.startswith('---') or s.startswith('```'):
                continue
            s = re.sub(r'!\[.*?\]\(.*?\)', '', s)
            s = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', s)
            s = re.sub(r'[*_`>|]+', '', s)
            s = re.sub(r'\s+', ' ', s).strip()
            if s:
                lines.append(s)
        summary = ' | '.join(lines)
        if not summary:
            return "Market signal: report generated, no summary lines extracted."
        if len(summary) > max_chars:
            summary = summary[:max_chars - 1] + '…'
        return summary

    # ---------- 入口 ----------
    def send_to_wechat_mp(self, content: str) -> bool:
        """发送公众号多字段模板消息"""
        if not all([
            self._wechat_mp_appid, self._wechat_mp_secret,
            self._wechat_mp_template_id, self._wechat_mp_user_openid,
        ]):
            logger.warning(
                "微信公众号模板消息未配置，跳过推送（需 WECHAT_MP_APPID/SECRET/TEMPLATE_ID/USER_OPENID）"
            )
            return False

        token = self._get_access_token()
        if not token:
            return False

        weather = self._get_weather()
        commentary = self._get_commentary(weather['code'])
        stock_summary = self._summarize(content)

        message = {
            "touser": self._wechat_mp_user_openid,
            "template_id": self._wechat_mp_template_id,
            "url": "",
            "topcolor": "#FF0000",
            "data": {
                "date":        {"value": self._get_local_time(), "color": "#173177"},
                "weather":     {"value": f"{weather['name']}, {weather['temp']} (feels like {weather['feels_like']})", "color": "#FF6347"},
                "remark":      {"value": f"Wind: {weather['wind']} | Humidity: {weather['humidity']}", "color": "#666666"},
                "destination": {"value": self._wechat_mp_destination_text, "color": "#888888"},
                "joke1":       {"value": commentary, "color": "#5B8DB8"},
                "joke2":       {"value": stock_summary, "color": "#2E7D32"},
            },
        }

        try:
            url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}"
            resp = requests.post(url, json=message, timeout=10).json()
            if resp.get('errcode') == 0:
                logger.info("微信公众号模板消息发送成功")
                return True
            logger.error("微信公众号模板消息发送失败: %s", resp)
        except Exception as e:
            logger.error("微信公众号模板消息发送异常: %s", e)
        return False
