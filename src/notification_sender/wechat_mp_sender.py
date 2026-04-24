# -*- coding: utf-8 -*-
"""
微信公众号模板消息发送服务（多字段模板）

模板格式（在公众号后台新建，每行一个变量，避免超宽被截）:
    It's {{date.DATA}}
    It's {{weather.DATA}}
    {{remark1.DATA}}
    {{remark2.DATA}}
    {{destination1.DATA}}
    {{destination2.DATA}}
    Murphy, today's briefing:
    - {{joke1.DATA}}
    - {{joke2.DATA}}

字段映射（每个字段独立一行，微信不会自动换行，所以需要代码预拆）:
    date         -> 当地时间
    weather      -> 天气 + 温度（含体感）
    remark1/2    -> 天气评语，预拆为两行
    destination1/2 -> Error 404 文案，预拆为两行
    joke1/2      -> 股票分析要点 × 2
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
    "Error 404: Bridge is under repair. "
    "Retrying with a better version soon."
)

# 微信模板消息单字段渲染上限：手机端约 38 个英文宽度，
# 但不同机型实际表现不同，这里只用来「拆句」，不主动截断，
# 超出字段交给微信自己渲染。
_FIELD_MAX_WIDTH = 38
# 填充到模板的定额变量个数
_REMARK_SLOTS = 3   # remark1 / remark2 / remark3
_DEST_SLOTS = 2     # destination1 / destination2
_JOKE_SLOTS = 7     # joke1 .. joke7（与股票模板变量数量保持一致）
# Lucky Color 加权概率（避免常年雨/晴天气下该类几乎不出现）
_LUCKY_COLOR_BIAS = 0.20


class WechatMpSender:

    def __init__(self, config: Config):
        self._wechat_mp_appid = getattr(config, 'wechat_mp_appid', None)
        self._wechat_mp_secret = getattr(config, 'wechat_mp_secret', None)
        self._wechat_mp_template_id = getattr(config, 'wechat_mp_template_id', None)
        self._wechat_mp_stock_template_id = getattr(config, 'wechat_mp_stock_template_id', None)
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
        # 天气评语：主要按天气选类别，加权让 lucky_color 也能随机出现
        if random.random() < _LUCKY_COLOR_BIAS:
            category = 'lucky_color'
        else:
            category = _WEATHER_CATEGORY.get(weather_code, 'mood')
        return random.choice(_COMMENTARY[category])

    # ---------- 摘要清洗 ----------
    @staticmethod
    def _extract_lines(content: str) -> list:
        """从 markdown 抽取清理后的有效行（保留顺序）。"""
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
            s = re.sub(r'^[-•]\s*', '', s)  # 去除 markdown 项目符号
            s = re.sub(r'\s+', ' ', s).strip()
            if s:
                lines.append(s)
        return lines

    # ---------- 显示宽度工具（中文 = 2 宽，其他 = 1）----------
    @staticmethod
    def _disp_width(text: str) -> int:
        w = 0
        for ch in text or '':
            cp = ord(ch)
            # CJK 统一表意 / 全角标点 / 偏旁部首等
            if (
                0x1100 <= cp <= 0x115F or
                0x2E80 <= cp <= 0x303E or
                0x3041 <= cp <= 0x33FF or
                0x3400 <= cp <= 0x4DBF or
                0x4E00 <= cp <= 0x9FFF or
                0xA000 <= cp <= 0xA4CF or
                0xAC00 <= cp <= 0xD7A3 or
                0xF900 <= cp <= 0xFAFF or
                0xFE30 <= cp <= 0xFE4F or
                0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6
            ):
                w += 2
            else:
                w += 1
        return w

    @classmethod
    def _split_by_width(cls, text: str, max_width: int, slots: int) -> list:
        """按显示宽度把 text 切成 ≤ slots 段，每段宽度 ≤ max_width。
        优先在空格处切，没空格就硬切。不足 slots 个补 '-'。
        若文本长到所有 slot 都装不下，最后一段把剩余全部塞进去（不加…，
        让微信自己渲染 / 必要时折叠）。"""
        text = (text or '').strip()
        if not text:
            return ['-'] * slots
        chunks = []
        remaining = text
        for slot_i in range(slots):
            if not remaining:
                break
            if cls._disp_width(remaining) <= max_width:
                chunks.append(remaining)
                remaining = ''
                break
            # 找一个在 max_width 内的空格切点
            best_cut = 0
            cur_w = 0
            last_space = 0
            for idx, ch in enumerate(remaining):
                cur_w += cls._disp_width(ch)
                if cur_w > max_width:
                    break
                if ch == ' ':
                    last_space = idx
                best_cut = idx + 1
            if last_space > best_cut // 2:
                cut = last_space
                chunks.append(remaining[:cut].rstrip())
                remaining = remaining[cut + 1:].lstrip()
            else:
                chunks.append(remaining[:best_cut].rstrip())
                remaining = remaining[best_cut:].lstrip()
        # 如果 slots 用完了还有剩余，把它追加到最后一段（不加…）
        if remaining and chunks:
            chunks[-1] = (chunks[-1] + ' ' + remaining).strip()
        # 填足 slots
        while len(chunks) < slots:
            chunks.append('-')
        return chunks

    @classmethod
    def _split_line_to_pieces(cls, text: str, max_width: int) -> list:
        """把单行按显示宽度切成若干段，每段 ≤ max_width。优先空格切。"""
        text = (text or '').strip()
        if not text:
            return []
        pieces = []
        remaining = text
        while remaining:
            if cls._disp_width(remaining) <= max_width:
                pieces.append(remaining)
                break
            best_cut = 0
            cur_w = 0
            last_space = 0
            for idx, ch in enumerate(remaining):
                cur_w += cls._disp_width(ch)
                if cur_w > max_width:
                    break
                if ch == ' ':
                    last_space = idx
                best_cut = idx + 1
            if last_space > best_cut // 2:
                cut = last_space
                pieces.append(remaining[:cut].rstrip())
                remaining = remaining[cut + 1:].lstrip()
            else:
                pieces.append(remaining[:best_cut].rstrip())
                remaining = remaining[best_cut:].lstrip()
        return pieces

    def _pick_summaries(self, content: str, slots: int) -> list:
        """从 markdown 报告中按章节提取股票简报内容填充槽位。

        提取规则（对应 joke1-7）:
          - 一、市场总结 → 首条有效句          (1 行)
          - 二、主要指数 → 各指数行，最多 4 条  (4 行)
          - 四、板块表现 → 领涨/领跌行，最多 2 条 (2 行)
        不足 slots 补 '-'，超出 slots 截断。
        """
        import re
        lines = self._extract_lines(content)

        # 按"一、""二、"等中文序号章节分组
        section_pattern = re.compile(r'^[一二三四五六七八九十]+[、.]')
        sections: dict = {}
        current_key: str = ''
        for line in lines:
            if section_pattern.match(line):
                current_key = line
                sections[current_key] = []
            elif current_key:
                sections[current_key].append(line)

        def get_sec(num_char: str) -> list:
            for key, val in sections.items():
                if key.startswith(num_char):
                    return val
            return []

        result: list = []
        # 一、市场总结 → joke1
        s1 = get_sec('一')
        result.append(s1[0] if s1 else '-')
        # 二、主要指数 → joke2-5（最多 4 条）
        s2 = get_sec('二')
        for i in range(4):
            result.append(s2[i] if i < len(s2) else '-')
        # 四、板块表现 → joke6-7（最多 2 条）
        s4 = get_sec('四')
        for i in range(2):
            result.append(s4[i] if i < len(s4) else '-')

        # 补足或截断到 slots
        while len(result) < slots:
            result.append('-')
        return result[:slots]

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
        remarks = self._split_by_width(commentary, _FIELD_MAX_WIDTH, _REMARK_SLOTS)
        dests = self._split_by_width(self._wechat_mp_destination_text, _FIELD_MAX_WIDTH, _DEST_SLOTS)
        # 统一清理：去掉可能导致字段不显示的控制符
        def _clean(text: str) -> str:
            text = (text or '').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
            text = ' '.join(text.split())
            return text or '-'

        api_url = f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={token}"

        # ---------- 消息 1：天气 / 个人内容 ----------
        data_personal: dict = {
            "date":    {"value": _clean(self._get_local_time()),                                                    "color": "#173177"},
            "weather": {"value": _clean(f"{weather['name']}, {weather['temp']} (feels {weather['feels_like']})"), "color": "#FF6347"},
        }
        for i, v in enumerate(remarks, 1):
            data_personal[f"remark{i}"] = {"value": _clean(v), "color": "#5B8DB8"}
        for i, v in enumerate(dests, 1):
            data_personal[f"destination{i}"] = {"value": _clean(v), "color": "#888888"}

        msg_personal = {
            "touser": self._wechat_mp_user_openid,
            "template_id": self._wechat_mp_template_id,
            "url": "https://mp.weixin.qq.com",
            "topcolor": "#FF0000",
            "data": data_personal,
        }
        logger.info("微信MP(个人)待发送字段: %s", list(data_personal.keys()))

        success = False
        try:
            resp1 = requests.post(api_url, json=msg_personal, timeout=10).json()
            logger.info("微信MP(个人)响应: %s", resp1)
            if resp1.get('errcode') == 0:
                logger.info("微信公众号个人消息发送成功 (msgid=%s)", resp1.get('msgid'))
                success = True
            else:
                logger.error("微信公众号个人消息发送失败: %s", resp1)
        except Exception as e:
            logger.error("微信MP(个人)消息发送异常: %s", e)

        # ---------- 消息 2：股票内容（需配置 WECHAT_MP_STOCK_TEMPLATE_ID）----------
        if self._wechat_mp_stock_template_id:
            jokes = self._pick_summaries(content, _JOKE_SLOTS)
            data_stock: dict = {}
            for i, v in enumerate(jokes, 1):
                data_stock[f"joke{i}"] = {"value": v, "color": "#2E7D32"}

            msg_stock = {
                "touser": self._wechat_mp_user_openid,
                "template_id": self._wechat_mp_stock_template_id,
                "url": "https://mp.weixin.qq.com",
                "topcolor": "#FF0000",
                "data": data_stock,
            }
            logger.info("微信MP(股票)待发送字段: %s", list(data_stock.keys()))
            try:
                resp2 = requests.post(api_url, json=msg_stock, timeout=10).json()
                logger.info("微信MP(股票)响应: %s", resp2)
                if resp2.get('errcode') == 0:
                    logger.info("微信公众号股票消息发送成功 (msgid=%s)", resp2.get('msgid'))
                    success = True
                else:
                    logger.error("微信公众号股票消息发送失败: %s", resp2)
            except Exception as e:
                logger.error("微信MP(股票)消息发送异常: %s", e)

        return success
