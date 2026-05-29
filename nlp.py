"""
Rule-based Chinese food text parser — no external API, no cost.
Uses jieba for word segmentation + regex for date/quantity extraction.
"""
import logging
import re
from datetime import date, timedelta

import jieba

logging.getLogger('jieba').setLevel(logging.ERROR)

# ── Units ─────────────────────────────────────────────────────────────────────

_FOOD_UNITS = [
    '公升', '毫升', '公克', '公斤',                          # multi-char first
    '瓶', '罐', '個', '包', '盒', '袋', '條', '片', '塊', '份',
    '顆', '粒', '串', '把', '支', '箱', '桶', '升', '克', '斤',
    '兩', '杯', '碗', '匙',
    'kg', 'ml', 'g', 'L',
]
UNIT_RE = '|'.join(re.escape(u) for u in _FOOD_UNITS)

for u in _FOOD_UNITS:
    jieba.add_word(u, freq=10000)

# ── Chinese numerals ──────────────────────────────────────────────────────────

_CN_NUM = {
    '零': 0, '○': 0, '〇': 0,
    '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9,
    '十': 10, '百': 100, '千': 1000,
    '半': 0.5,
}

_NUM_RE = r'([一二三四五六七八九十百千兩半\d][一二三四五六七八九十百千兩半\d\.]*)'

_STOP = set('的了是在我你他她它們個一就也都和或但而呢嗎吧啊喔想要有沒不')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fw2hw(text: str) -> str:
    """Full-width → half-width digits/letters."""
    return ''.join(chr(ord(c) - 0xFEE0) if '！' <= c <= '～' else c for c in text)


def _to_float(s: str) -> float:
    s = _fw2hw(s).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if s == '半':
        return 0.5
    if len(s) == 1 and s in _CN_NUM:
        return float(_CN_NUM[s])
    # Compound Chinese: 十二 / 二十五 / 一百五十
    val, cur = 0, 0
    for c in s:
        n = _CN_NUM.get(c, -1)
        if n < 0:
            continue
        if n >= 10:
            val += (cur if cur else 1) * n
            cur = 0
        else:
            cur = n
    total = val + cur
    return float(total) if total > 0 else 1.0


def _safe_date(y, m, d):
    """Safely create a date, returning None on invalid input."""
    try:
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _date_from_md(month, day, today):
    """Create date from month/day; if already passed this year, use next year."""
    try:
        d = date(today.year, int(month), int(day))
        if d < today:
            d = date(today.year + 1, int(month), int(day))
        return d
    except (ValueError, TypeError):
        return None


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_food_text(text: str) -> dict:
    today = date.today()
    text = _fw2hw(text).strip()

    result = {
        'name':          '',
        'quantity':      1.0,
        'unit':          '個',
        'purchase_date': None,
        'expiry_date':   None,
        'location_hint': None,
    }

    # Spans to blank out before name extraction
    masked = list(text)

    def _mask(m):
        for i in range(m.start(), m.end()):
            masked[i] = ' '

    # ── Purchase date ──────────────────────────────────────────────
    purchase_date = None
    for pat, fn in [
        (r'大前天',                                        lambda _: today - timedelta(days=3)),
        (r'前天',                                          lambda _: today - timedelta(days=2)),
        (r'昨天|昨日',                                     lambda _: today - timedelta(days=1)),
        (r'今天|今日|今早|今晚|早上買|下午買|剛才|剛剛',   lambda _: today),
        (rf'{_NUM_RE}\s*天前',                             lambda m: today - timedelta(days=int(_to_float(m.group(1))))),
        (rf'{_NUM_RE}\s*(?:個[週周]|[週周]|禮拜|星期)前', lambda m: today - timedelta(weeks=int(_to_float(m.group(1))))),
    ]:
        m = re.search(pat, text)
        if m:
            purchase_date = fn(m)
            _mask(m)
            break

    # Has buying verb but no explicit date → assume today
    if purchase_date is None and re.search(r'買了?|購買了?|採購了?|買回來', text):
        purchase_date = today

    result['purchase_date'] = purchase_date.isoformat() if purchase_date else None

    # ── Expiry date ────────────────────────────────────────────────
    expiry_date = None

    # Explicit "no expiry" → mask and leave expiry null
    no_exp = re.search(
        r'沒有?期限|無[效有]?期[限]?|沒有?效期|永久保存|不會到期|應該沒有?期|沒有?到期日',
        text
    )
    if no_exp:
        _mask(no_exp)
    else:
        for pat, fn in [
            # ── 1. Absolute dates ──────────────────────────────────────
            # 有效期限到/效期到/保存期限到 YYYY年M月D日
            (r'(?:有效期限?[到至]|效期[到至]|保存期限?[到至]|到期[日為：:]\s*)'
             r'\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]?',
             lambda m: _safe_date(m.group(1), m.group(2), m.group(3))),
            # YYYY年M月D日 到期/過期
            (r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]?\s*(?:[到過]期)',
             lambda m: _safe_date(m.group(1), m.group(2), m.group(3))),
            # Bare YYYY年M月D日
            (r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]?',
             lambda m: _safe_date(m.group(1), m.group(2), m.group(3))),
            # YYYY/M/D or YYYY-M-D
            (r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',
             lambda m: _safe_date(m.group(1), m.group(2), m.group(3))),
            # M月D日 到期 (infer year)
            (r'(\d{1,2})\s*月\s*(\d{1,2})\s*[日號]?\s*(?:[到過]期)',
             lambda m: _date_from_md(m.group(1), m.group(2), today)),

            # ── 2. Named relative dates ────────────────────────────────
            (r'明天[到過]期|後天[到過]期',
             lambda m: today + timedelta(days=1 if '明天' in m.group() else 2)),
            (r'下[個]?(?:週|周|星期)[到過]?期?|一[個]?(?:週|周)後[到過]?期?',
             lambda _: today + timedelta(weeks=1)),
            (r'下個?月[到過]?期?|一個?月後[到過]?期?',
             lambda _: today + timedelta(days=30)),
            (r'半個?月(?:後|內)?[到過]?期?',
             lambda _: today + timedelta(days=15)),

            # ── 3. Prefixed storage phrases (MUST come before bare N+unit) ──
            # 保存 N 天/週/月
            (rf'保存{_NUM_RE}\s*天',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'保存{_NUM_RE}\s*個?(?:禮拜|週|周|星期)',
             lambda m: today + timedelta(weeks=int(_to_float(m.group(1))))),
            (rf'保存{_NUM_RE}\s*個?月',
             lambda m: today + timedelta(days=int(_to_float(m.group(1)) * 30))),
            # 可以放 N 天/週/月
            (rf'可以放{_NUM_RE}\s*天',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'可以放{_NUM_RE}\s*個?(?:禮拜|週|周)',
             lambda m: today + timedelta(weeks=int(_to_float(m.group(1))))),
            (rf'可以放{_NUM_RE}\s*個?月',
             lambda m: today + timedelta(days=int(_to_float(m.group(1)) * 30))),
            # 可存放 N 天/週
            (rf'約?可存放{_NUM_RE}\s*天',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'約?可存放{_NUM_RE}\s*個?(?:禮拜|週|周)',
             lambda m: today + timedelta(weeks=int(_to_float(m.group(1))))),
            # 效期 N 天
            (rf'效期{_NUM_RE}\s*[天日]',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),

            # ── 4. Fuzzy prefix (大約/大概) ────────────────────────────
            (rf'大[約概]?\s*{_NUM_RE}\s*個?(?:禮拜|週|周|星期)(?:後|內)?(?:[到過]期)?',
             lambda m: today + timedelta(weeks=int(_to_float(m.group(1))))),
            (rf'大[約概]?\s*{_NUM_RE}\s*天(?:後|內)?(?:[到過]期)?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'大[約概]?\s*{_NUM_RE}\s*個?月(?:後|內)?(?:[到過]期)?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1)) * 30))),

            # ── 5. Bare N + time unit ──────────────────────────────────
            (rf'{_NUM_RE}\s*個?(?:禮拜|週|周|星期)(?:後|內)?[到過]?期?',
             lambda m: today + timedelta(weeks=int(_to_float(m.group(1))))),
            (rf'{_NUM_RE}\s*天後[到過]?期?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'{_NUM_RE}\s*天內[到過]?期?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'(?:還有|再過)\s*{_NUM_RE}\s*天[到過]?期?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1))))),
            (rf'{_NUM_RE}\s*個?月後[到過]?期?',
             lambda m: today + timedelta(days=int(_to_float(m.group(1)) * 30))),
        ]:
            m = re.search(pat, text)
            if m:
                expiry_date = fn(m)
                _mask(m)
                break

    result['expiry_date'] = expiry_date.isoformat() if expiry_date else None

    # ── Quantity + unit ────────────────────────────────────────────
    # Search masked text to skip spans already consumed by date patterns
    masked_text = ''.join(masked)
    m = re.search(rf'{_NUM_RE}\s*({UNIT_RE})', masked_text)
    if m:
        result['quantity'] = _to_float(m.group(1))
        result['unit']     = m.group(2)
        for i in range(m.start(), m.end()):
            masked[i] = ' '

    # ── Location hint ──────────────────────────────────────────────
    for hint, kws in [
        ('冰箱',   ['冰箱', '冷藏']),
        ('冷凍庫', ['冷凍', '冷凍庫', '冷凍室']),
        ('乾貨櫃', ['乾貨', '儲藏', '櫥櫃', '常溫', '架上']),
    ]:
        if any(kw in text for kw in kws):
            result['location_hint'] = hint
            break

    # ── Name extraction ────────────────────────────────────────────
    name_text = ''.join(masked)

    for pat in [
        r'我[們]?',
        r'買了?|購買了?|採購了?|剛買了?|剛剛買了?|買回來',
        r'到期了?|過期了?|壞掉了?|壞了',
        r'放[在到]?(?:冰箱|冷藏|冷凍|乾貨|儲藏|常溫)*',
        r'冰箱|冷藏|冷凍|乾貨|儲藏|常溫',
        r'大約|大概|應該是?|差不多|約莫',
        r'有效期限?[到至]?|效期[到至]?|保存期限?[到至]?',
        r'沒有?期限|無[效有]?期[限]?|沒有?效期|永久保存',
    ]:
        name_text = re.sub(pat, ' ', name_text)

    name_text = re.sub(r'[，。！？,.!?\s]+', ' ', name_text).strip()
    name_text = re.sub(r'\s+', ' ', name_text).strip()

    if name_text:
        words = [
            w.strip() for w in jieba.cut(name_text)
            if w.strip() and w.strip() not in _STOP
            and not re.fullmatch(r'[\s，。！？,.!?]+', w)
        ]
        name = ''.join(words).strip()
    else:
        name = ''

    result['name'] = name if name else '未知食物'
    return result


# ── Batch parser ──────────────────────────────────────────────────────────────

def _split_items(text: str) -> list:
    """Split a sentence describing several food items into per-item segments."""

    # 1. Explicit 、 separator
    if '、' in text:
        parts = [p.strip() for p in text.split('、') if p.strip()]
        if len(parts) > 1:
            return parts

    # 2. Explicit connectors: 還有 / 另外 / 以及
    #    But skip if the right side is just a time expression (e.g. "還有五天到期")
    m = re.search(r'\s*(?:還有|另外|以及)\s*', text)
    if m:
        left  = text[:m.start()].strip()
        right = text[m.end():].strip()
        _time_only = re.compile(
            rf'^{_NUM_RE}\s*(?:天|週|周|月|禮拜|年|小時|hr)[到過內後]?期?'
        )
        if left and right and not _time_only.match(right):
            return [left, right]

    # 3. 和/跟 — only when BOTH sides contain a qty+unit pattern
    m = re.search(r'\s*[和跟]\s*', text)
    if m:
        left  = text[:m.start()].strip()
        right = text[m.end():].strip()
        qty_re = re.compile(rf'{_NUM_RE}\s*(?:{UNIT_RE})')
        if qty_re.search(left) and qty_re.search(right):
            return [left, right]

    # 4. Implicit boundary: items start with NUM+FOOD_UNIT.
    #    Exclude "個" followed by time words (e.g. 兩個禮拜, 三個月).
    boundary_re = re.compile(
        rf'{_NUM_RE}\s*({UNIT_RE})(?!\s*(?:禮拜|週|周|月|年|天|日))'
    )
    matches = list(boundary_re.finditer(text))
    if len(matches) > 1:
        splits = [m.start() for m in matches]
        parts = []
        for i, start in enumerate(splits):
            end = splits[i + 1] if i + 1 < len(splits) else len(text)
            part = text[start:end].strip()
            if part:
                parts.append(part)
        if len(parts) > 1:
            return parts

    return [text]


def parse_multiple_foods(text: str) -> list:
    """Parse a sentence describing one or more food items.

    Returns a list of item dicts (same format as parse_food_text).
    Shares global purchase-date and location context across items.
    """
    today = date.today()
    text = _fw2hw(text).strip()

    # ── Extract global context ─────────────────────────────────────
    global_ctx: dict = {}

    for pat, fn in [
        (r'大前天',                                        lambda _: today - timedelta(days=3)),
        (r'前天',                                          lambda _: today - timedelta(days=2)),
        (r'昨天|昨日',                                     lambda _: today - timedelta(days=1)),
        (r'今天|今日|今早|今晚|早上|下午',                 lambda _: today),
        (rf'{_NUM_RE}\s*天前',                             lambda m: today - timedelta(days=int(_to_float(m.group(1))))),
        (rf'{_NUM_RE}\s*(?:個[週周]|[週周]|禮拜|星期)前', lambda m: today - timedelta(weeks=int(_to_float(m.group(1))))),
    ]:
        if re.search(pat, text):
            global_ctx['purchase_date'] = fn(re.search(pat, text)).isoformat()
            break

    if 'purchase_date' not in global_ctx and re.search(r'買了?|購買了?|採購了?|買回來', text):
        global_ctx['purchase_date'] = today.isoformat()

    for hint, kws in [
        ('冰箱',   ['冰箱', '冷藏']),
        ('冷凍庫', ['冷凍', '冷凍庫']),
        ('乾貨櫃', ['乾貨', '儲藏', '常溫']),
    ]:
        if any(kw in text for kw in kws):
            global_ctx['location_hint'] = hint
            break

    # ── Split & parse each segment ────────────────────────────────
    segments = _split_items(text)
    results  = []

    for seg in segments:
        item = parse_food_text(seg)
        if item['purchase_date'] is None and 'purchase_date' in global_ctx:
            item['purchase_date'] = global_ctx['purchase_date']
        if item['location_hint'] is None and 'location_hint' in global_ctx:
            item['location_hint'] = global_ctx['location_hint']
        if item['name'] and item['name'] != '未知食物':
            results.append(item)

    # Fallback: treat whole text as a single item
    if not results:
        results = [parse_food_text(text)]

    return results


# Pre-warm jieba's dictionary on import (avoids slow first request)
jieba.lcut('測試', cut_all=False)
