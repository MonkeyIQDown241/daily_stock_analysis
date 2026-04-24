# -*- coding: utf-8 -*-
import sys; sys.path.insert(0, '.')
from src.notification_sender.wechat_mp_sender import WechatMpSender

class FakeCfg:
    wechat_mp_appid = None; wechat_mp_secret = None
    wechat_mp_template_id = None; wechat_mp_stock_template_id = None
    wechat_mp_user_openid = None; wechat_mp_city_id = '0,0'
    wechat_mp_timezone = 'UTC'; wechat_mp_destination_text = None

sender = WechatMpSender(FakeCfg())

# 模板报告格式（_generate_template_review 生成）
TEMPLATE_REPORT = """## 2026-04-24 大盘复盘

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

# LLM 报告格式（章节标题不同，内容也不同）
LLM_REPORT = """## 2026-04-24 大盘复盘

### 一、市场总结
今日A股市场整体小幅下跌，成交量萎缩，市场情绪偏谨慎。

### 二、指数点评
上证指数收于4093.25点，跌幅0.32%。
深证成指收于15043.45点，跌幅0.88%。
创业板指收于3720.25点，跌幅0.87%。
科创50收于1432.59点，跌幅1.28%。

### 三、资金动向
两市成交28233亿，较前日略有萎缩。

### 四、热点解读
领涨板块：食用菌、风力发电、油气及炼化工程。
领跌板块：稀土、白银、钼。

### 五、风险提示
注意风险。
"""

for label, rpt in [('模板报告', TEMPLATE_REPORT), ('LLM报告', LLM_REPORT)]:
    print(f'\n=== {label} ===')
    for i, s in enumerate(sender._pick_summaries(rpt, 7), 1):
        print(f'  joke{i}: {s}')
