"""
Gemini-based food text parser.
Uses google-genai SDK. Activated when NLP_BACKEND=gemini in environment.
Output format is identical to parse_multiple_foods() in nlp.py.
"""
import json
import os
from datetime import date

from google import genai
from google.genai import types


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    return f"""你是食物庫存解析助手。今天是 {today}（台灣時間）。

從使用者輸入中解析出所有食物，只回傳 JSON 陣列（不要任何說明文字、不要 markdown code fence）。
每個物件包含以下欄位：

  name          : string   食物名稱（純名詞，去掉所有數量/日期/動詞/形容詞）
  quantity      : number   數量（浮點數，預設 1.0）
  unit          : string   單位（個/包/顆/瓶/公克/公斤/條/片/根/隻…，預設「個」）
  purchase_date : string|null  購買日期 YYYY-MM-DD；出現購買動詞（買、採購、入手、買了、買回來）且無明確日期→今天；否則 null
  expiry_date   : string|null  到期/保存期限日期 YYYY-MM-DD；相對日期（三天後/一禮拜/下週/一個月後）請從今天 {today} 計算成絕對日期；「沒有期限/無期限/永久」→ null
  location_hint : string|null  存放地點，只能是「冰箱」「冷凍庫」「乾貨櫃」之一；未提及→ null

解析規則：
1. 一段文字含多種食物 → 每種食物各一個物件
2. 全局時間描述（如「這些大概都是一個禮拜到期」）套用到所有沒有個別到期日的品項
3. 只回傳 JSON 陣列，陣列中每個元素就是一個食物物件
4. quantity 必須是 number（不是 string）
5. 日期欄位必須是 "YYYY-MM-DD" 格式的字串或 null（不接受其他格式）
6. 若整段文字無法解析出任何食物，回傳空陣列 []"""


def _validate_items(items: list) -> list:
    """Ensure every field has the correct type to match nlp.py output."""
    result = []
    for it in (items or []):
        name = str(it.get('name') or '未知食物').strip()
        if not name:
            name = '未知食物'
        result.append({
            'name':          name,
            'quantity':      float(it.get('quantity') or 1.0),
            'unit':          str(it.get('unit') or '個'),
            'purchase_date': it.get('purchase_date') or None,
            'expiry_date':   it.get('expiry_date')   or None,
            'location_hint': it.get('location_hint') or None,
        })
    return result


def parse_with_gemini(text: str) -> list[dict]:
    """Parse food text using Gemini Flash. Returns same format as parse_multiple_foods()."""
    api_key    = os.environ.get('GEMINI_API_KEY', '')
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
            temperature=0,           # 確定性輸出
            response_mime_type='application/json',
        ),
    )

    raw = (response.text or '').strip()

    # Strip markdown code fence if model ignores mime_type hint
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        raw = raw.rsplit('```', 1)[0].strip()

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f'Gemini 回傳無效 JSON：{e}\n原始回應：{raw[:300]}')

    if not isinstance(items, list):
        items = [items]

    validated = _validate_items(items)
    if not validated:
        raise ValueError('Gemini 未解析出任何食物')

    return validated
