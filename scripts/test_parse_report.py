# -*- coding: utf-8 -*-
import sys; sys.path.insert(0, '.')
from src.notification_sender.wechat_mp_sender import WechatMpSender

class FakeCfg:
    wechat_mp_appid = None; wechat_mp_secret = None
    wechat_mp_template_id = None; wechat_mp_stock_template_id = None
    wechat_mp_user_openid = None; wechat_mp_city_id = '0,0'
    wechat_mp_timezone = 'UTC'; wechat_mp_destination_text = None

sender = WechatMpSender(FakeCfg())

# 1. 模板报告（无LLM，_generate_template_review 输出）
TEMPLATE_REPORT = """🎯 大盘复盘

## 2026-04-24 大盘复盘

### 一、市场总结
今日A股市场整体呈现**小幅下跌**态势。

### 二、主要指数
- **上证指数**: 4093.25 (↓0.32%)
- **深证成指**: 15043.45 (↓0.88%)
- **创业板指**: 3720.25 (↓0.87%)
- **科创50**: 1432.59 (↓1.28%)

### 三、涨跌统计
| 指标 | 数值 |
|------|------|
| 上涨家数 | 1330 |

### 四、板块表现
- **领涨**: 食用菌、风力发电、油气及炼化工程
- **领跌**: 稀土、白银、钼

### 五、风险提示
市场有风险，投资需谨慎。
"""

# 2. LLM报告 + _inject_data_into_review 注入后的格式
LLM_INJECTED_REPORT = """🎯 大盘复盘

## 2026-04-24 大盘复盘

### 一、市场总结
今日A股市场整体呈现小幅下跌态势，各主要指数均收跌，成交额有所萎缩。

> 📈 上涨 **1330** 家 / 下跌 **4078** 家 / 平盘 **190** 家 | 涨停 **59** / 跌停 **31** | 成交额 **28233** 亿

### 二、指数点评
今日上证指数小幅下探，深证成指和创业板跌幅居前，科创50领跌。

| 指数 | 最新 | 涨跌幅 | 成交额(亿) |
|------|------|--------|-----------|
| 上证指数 | 4093.25 | 🔴 -0.32% | 12340 |
| 深证成指 | 15043.45 | 🔴 -0.88% | 9870 |
| 创业板指 | 3720.25 | 🔴 -0.87% | 4521 |
| 科创50 | 1432.59 | 🔴 -1.28% | 1502 |

### 三、资金动向
两市成交28233亿，较前日略有萎缩，市场人气偏弱。

### 四、热点解读
食用菌、风力发电等板块逆市上涨，稀土、白银板块资金持续流出。

> 🔥 领涨: **食用菌**(+3.21%) | **风力发电**(+2.87%) | **油气及炼化工程**(+1.54%)
> 💧 领跌: **稀土**(-2.13%) | **白银**(-1.87%) | **钼**(-1.65%)

### 五、后市展望
短期仍有调整压力，关注政策面变化。

### 六、风险提示
市场有风险，投资需谨慎。
"""

for label, rpt in [('模板报告', TEMPLATE_REPORT), ('LLM+注入报告', LLM_INJECTED_REPORT)]:
    print(f'\n=== {label} ===')
    for i, s in enumerate(sender._pick_summaries(rpt, 7), 1):
        print(f'  joke{i}: {s}')
