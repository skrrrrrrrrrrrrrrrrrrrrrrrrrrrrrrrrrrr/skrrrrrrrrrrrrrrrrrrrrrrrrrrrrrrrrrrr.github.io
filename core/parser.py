"""키워드 기반 자연어 분석기. 나중에 AI API 분석기로 교체할 수 있도록 parse_query()만 노출한다."""
import calendar
import re
from datetime import date, timedelta
from typing import Optional

from .models import ParsedQuery

DOMAIN_KEYWORDS = {
    "weather": ["날씨", "기온", "온도", "강수", "강우", "비가", "습도", "풍속", "바람", "기상"],
    "population": ["인구", "출생", "사망", "가구", "연령"],
    "health": ["감염병", "예방접종", "질병", "독감", "코로나", "확진", "발생 현황", "발생현황"],
}

# 지역 -> 기상청 ASOS 지점번호
REGIONS = {
    "서울": "108", "부산": "159", "대구": "143", "인천": "112", "광주": "156",
    "대전": "133", "울산": "152", "세종": "239", "수원": "119", "춘천": "101",
    "강릉": "105", "청주": "131", "전주": "146", "제주": "184", "목포": "165",
    "포항": "138",
}

WEATHER_METRICS = [
    (["평균기온", "평균 기온", "평균온도"], "avg_temp"),
    (["최고기온", "최고 기온"], "max_temp"),
    (["최저기온", "최저 기온"], "min_temp"),
    (["강수량", "강수", "강우", "비가", "비는", "비도", "얼마나 왔"], "rain"),
    (["습도"], "humidity"),
    (["풍속", "바람"], "wind"),
]
GENERIC_TEMP = ["기온", "온도"]
RELATION_WORDS = ["관계", "상관", "산점도"]


def detect_domain(text: str) -> Optional[str]:
    scores = {d: sum(text.count(k) for k in ks) for d, ks in DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def detect_region(text: str) -> Optional[str]:
    for name in REGIONS:
        if name in text:
            return name
    return None


def detect_weather_metrics(text: str) -> list:
    found = []
    for kws, key in WEATHER_METRICS:
        if any(k in text for k in kws) and key not in found:
            found.append(key)
    if not found and any(k in text for k in GENERIC_TEMP):
        found.append("avg_temp")
    return found


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def detect_period(text: str, today: Optional[date] = None):
    """(start, end, 라벨, 경고목록) 반환. 못 찾으면 start=None."""
    today = today or date.today()
    warns = []

    m = re.search(r"(\d{4})\s*년\s*부터\s*(\d{4})\s*년", text)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y1 > y2:
            y1, y2 = y2, y1
        return date(y1, 1, 1), date(y2, 12, 31), f"{y1}년~{y2}년", warns

    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            warns.append(f"{mo}월은 올바른 월이 아닙니다. 1~12 사이로 입력해주세요.")
            return None, None, "", warns
        return date(y, mo, 1), date(y, mo, _last_day(y, mo)), f"{y}년 {mo}월", warns

    m = re.search(r"최근\s*(\d+)\s*(년|개월|달|일)", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * 365 if unit == "년" else n * 30 if unit in ("개월", "달") else n
        return today - timedelta(days=days), today, f"최근 {n}{unit}", warns
    if "최근 몇 년" in text:
        return today - timedelta(days=365 * 5), today, "최근 5년", warns

    m = re.search(r"(\d{4})\s*년", text)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31), f"{y}년", warns

    return None, None, "", warns


def parse_query(text: str, today: Optional[date] = None) -> ParsedQuery:
    text = (text or "").strip()
    q = ParsedQuery(raw=text)
    q.domain = detect_domain(text)
    q.region = detect_region(text)
    q.start, q.end, q.period_label, warns = detect_period(text, today)
    q.warnings.extend(warns)
    q.wants_relation = any(w in text for w in RELATION_WORDS)
    if q.domain == "weather":
        q.metrics = detect_weather_metrics(text)
    return q
