"""名称解析：把自然语言中的城市 / 车站 / 线路名解析成站点实体。

包含三部分：
1. `resolve_city` / `resolve_station` / `resolve_line`：模糊匹配；
2. `parse_intent`：从中文问句里抽取「城市 + 起点 + 终点 + 时间模式」；
3. 地标别名词表：把「首都机场」这类口语说法映射到站名「3号航站楼」。
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import City, Line, Station

# --------------------------------------------------------------------- 归一化

_PUNCT_RE = re.compile(r"[\s\-_·・()（）\[\]【】,，。.!！?？:：;；'\"/\\|+]+")


def normalize(text: str) -> str:
    """归一化：全角转半角、去空白与标点、转小写。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    return _PUNCT_RE.sub("", text)


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _char_overlap(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


# ------------------------------------------------------------------ 地标词表

#: 口语地标 -> 该城市内可能对应的站名（按优先级）
KNOWN_LANDMARKS: Dict[str, List[str]] = {
    # 北京
    "首都机场": ["3号航站楼", "2号航站楼"],
    "首都国际机场": ["3号航站楼", "2号航站楼"],
    "首都机场t3": ["3号航站楼"],
    "首都机场t2": ["2号航站楼"],
    "大兴国际机场": ["大兴机场"],
    "北京南站": ["北京南站"],
    "北京西站": ["北京西站"],
    "北京站": ["北京站"],
    # 上海
    "虹桥机场": ["虹桥1号航站楼", "虹桥2号航站楼", "虹桥火车站"],
    "虹桥火车站": ["虹桥火车站"],
    "浦东机场": ["浦东1号2号航站楼"],
    "浦东国际机场": ["浦东1号2号航站楼"],
    "上海火车站": ["上海火车站"],
    "上海南站": ["上海南站"],
    "人民广场": ["人民广场"],
    "外滩": ["豫园"],
    # 广州 / 深圳
    "白云机场": ["机场北(2号航站楼)", "机场南", "机场北"],
    "广州火车站": ["广州火车站"],
    "深圳宝安机场": ["机场", "机场东", "机场北"],
    "深圳北站": ["深圳北站"],
    # 成都
    "双流机场": ["双流机场1航站楼", "双流机场2航站楼"],
    "天府机场": ["天府机场1号2号航站楼", "天府机场北"],
    "成都东站": ["成都东站"],
    # 重庆
    "江北机场": ["江北机场T2航站楼", "江北机场T3航站楼"],
    "重庆北站": ["重庆北站"],
    # 其它
    "萧山机场": ["萧山国际机场"],
    "黄花机场": ["黄花机场T1T2"],
    "新郑机场": ["新郑机场"],
    "禄口机场": ["禄口机场"],
    "滨海机场": ["滨海国际机场"],
    "胶东机场": ["胶东机场"],
    "桃仙机场": ["桃仙机场"],
    "昌北机场": ["昌北机场"],
    "龙洞堡机场": ["龙洞堡机场"],
    "栎社机场": ["栎社国际机场"],
    "武宿机场": ["武宿1号2号航站楼"],
}

#: 地标类别 -> 站名中可能出现的关键词（用于泛化匹配）
LANDMARK_KINDS: Dict[str, List[str]] = {
    "机场": ["机场", "航站楼", "航厦", "空港", "国际机场"],
    "火车站": ["火车站", "高铁站", "铁路站"],
    "大学": ["大学", "学院"],
    "医院": ["医院"],
    "博物馆": ["博物馆", "美术馆", "纪念馆", "展览馆", "科技馆", "艺术馆"],
    "公园": ["公园"],
    "会展": ["会展", "博览", "展览"],
    "体育": ["体育场", "体育馆", "体育中心"],
    "广场": ["广场"],
}

#: 出现在问句里时需要先剥掉的时间/方式词
_STOPWORDS = [
    "请问", "麻烦", "帮我", "我想", "我要", "想要", "打算", "准备",
    "今天", "明天", "后天", "现在", "目前", "最近",
    "早上", "上午", "中午", "下午", "傍晚", "晚上", "夜里", "凌晨",
    "怎么", "如何", "怎样", "多少", "多久", "多长时间", "多长",
    "坐", "乘", "搭", "换乘", "转乘", "地铁", "公交", "出行", "路线", "方案",
    "最快", "最快��", "最省", "省时", "省钱", "方便", "推荐",
    "出发", "到达", "抵达", "到达站", "出发站", "起点", "终点", "目的地",
    "的话", "有吗", "谢谢",
    "首班车", "末班车", "首班", "末班", "第一班", "最后一班",
]


# --------------------------------------------------------------------- 城市


def resolve_city(query: str, cities: Sequence[City]) -> City:
    """按中文名 / 英文名 / key / id 解析城市。"""
    norm = normalize(query)
    if not norm:
        raise ValueError("城市不能为空")

    for city in cities:
        if norm == normalize(city.name) or norm == normalize(city.en):
            return city
    for city in cities:
        if norm == normalize(city.key) or norm == normalize(city.id):
            return city

    scored = []
    for city in cities:
        best = max(
            _ratio(norm, normalize(city.name)),
            _ratio(norm, normalize(city.en)),
            _ratio(norm, normalize(city.key)),
            _ratio(norm, normalize(city.id)),
        )
        scored.append((best, city))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 0.6:
        return scored[0][1]
    raise ValueError(f"未找到城市：{query}")


def find_city_mentions(text: str, cities: Sequence[City]) -> List[Tuple[int, City]]:
    """在文本中找出所有城市提及位置（按长度从长到短，避免「北京」抢「南京」）。"""
    hits: List[Tuple[int, City]] = []
    for city in cities:
        for alias in (city.name, city.en, city.key):
            if not alias:
                continue
            start = 0
            while True:
                idx = text.find(alias, start)
                if idx < 0:
                    break
                hits.append((idx, city, len(alias)))
                start = idx + 1
    # 同位置优先取更长匹配
    hits.sort(key=lambda item: (-item[2], item[0]))
    result: List[Tuple[int, City]] = []
    used: List[Tuple[int, int]] = []
    for idx, city, length in hits:
        span = (idx, idx + length)
        if any(span[0] < u[1] and u[0] < span[1] for u in used):
            continue
        used.append(span)
        result.append((idx, city))
    result.sort(key=lambda item: item[0])
    return result


# --------------------------------------------------------------------- 车站


@dataclass
class StationMatch:
    station: Station
    score: float
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slug": self.station.slug,
            "name": self.station.name,
            "en": self.station.en,
            "score": round(self.score, 3),
            "reason": self.reason,
        }


def _station_aliases(station: Station) -> List[str]:
    aliases = [station.name, station.slug, station.en]
    aliases.extend(station.aliases)
    seen = set()
    result = []
    for alias in aliases:
        key = normalize(alias)
        if key and key not in seen:
            seen.add(key)
            result.append(alias)
    return result


def resolve_station(
    query: str,
    stations: Sequence[Station],
    limit: int = 5,
) -> List[StationMatch]:
    """把一个名称（可能是模糊说法）解析成候选车站列表。"""
    norm = normalize(query)
    if not norm or not stations:
        return []

    known_phrases = _known_landmark_matches(query, stations)

    matches: List[StationMatch] = []
    for station in stations:
        best_score = 0.0
        best_reason = ""
        for alias in _station_aliases(station):
            alias_norm = normalize(alias)
            if not alias_norm:
                continue
            if alias_norm == norm:
                best_score, best_reason = 1.0, f"完全匹配（{alias}）"
                break
            if norm in alias_norm:
                score = 0.70 + 0.25 * (len(norm) / len(alias_norm))
                if score > best_score:
                    best_score, best_reason = score, f"包含匹配（{alias}）"
            elif alias_norm in norm:
                score = 0.60 + 0.25 * (len(alias_norm) / len(norm))
                if score > best_score:
                    best_score, best_reason = score, f"被包含（{alias}）"
            else:
                score = _ratio(norm, alias_norm)
                if score > best_score:
                    best_score, best_reason = score, f"近似匹配（{alias}）"

        # 地标别名（如「首都机场」->「3号航站楼」）优先级最高
        known_score = _known_landmark_score(station, known_phrases)
        if known_score > 0:
            best_score, best_reason = known_score, "地标别名匹配"
        else:
            # 泛化地标类别（如「XX机场」-> 含「机场/航站楼」的车站）
            kind_score = _landmark_boost(query, station)
            if kind_score > best_score:
                best_score, best_reason = kind_score, "地标类别匹配"

        if best_score > 0:
            matches.append(StationMatch(station, best_score, best_reason))

    matches.sort(key=lambda m: m.score, reverse=True)

    # 命中已知地标别名时，只保留别名命中的候选
    if known_phrases:
        filtered = [m for m in matches if m.reason == "地标别名匹配"]
        if filtered:
            matches = filtered

    return matches[:limit]


def _known_landmark_matches(query: str, stations: Sequence[Station]) -> List[str]:
    """命中的地标别名短语列表。"""
    norm = normalize(query)
    hits = []
    for phrase in KNOWN_LANDMARKS:
        phrase_norm = normalize(phrase)
        if phrase_norm and phrase_norm in norm:
            hits.append(phrase)
    return hits


def _known_landmark_score(station: Station, phrases: Sequence[str]) -> float:
    name_norm = normalize(station.name)
    best = 0.0
    for phrase in phrases:
        for index, candidate in enumerate(KNOWN_LANDMARKS[phrase]):
            if normalize(candidate) == name_norm:
                best = max(best, 0.99 - index * 0.01)
    return best


def _landmark_boost(query: str, station: Station) -> float:
    """地标别名 / 类别匹配提权。"""
    norm = normalize(query)
    if not norm:
        return 0.0
    name_norm = normalize(station.name)

    for phrase, candidates in KNOWN_LANDMARKS.items():
        phrase_norm = normalize(phrase)
        if phrase_norm and phrase_norm in norm:
            for index, candidate in enumerate(candidates):
                if normalize(candidate) == name_norm:
                    return 0.99 - index * 0.01

    best = 0.0
    for kind, keywords in LANDMARK_KINDS.items():
        if normalize(kind) not in norm:
            continue
        for keyword in keywords:
            if keyword in station.name:
                qualifier = norm.replace(normalize(kind), "")
                overlap = _char_overlap(qualifier, name_norm)
                score = 0.62 + 0.2 * overlap
                best = max(best, score)
    return best


# --------------------------------------------------------------------- 线路


def resolve_line(query: str, lines: Sequence[Line], limit: int = 5) -> List[Line]:
    """按名称 / 编号 / 英文名解析线路。"""
    norm = normalize(query)
    scored: List[Tuple[float, Line]] = []
    for line in lines:
        candidates = [line.name, line.code, line.en, line.slug]
        best = 0.0
        for alias in candidates:
            if not alias:
                continue
            alias_norm = normalize(alias)
            if alias_norm == norm:
                best = 1.0
                break
            if norm in alias_norm:
                best = max(best, 0.75)
            else:
                best = max(best, _ratio(norm, alias_norm))
        if best > 0:
            scored.append((best, line))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [line for _, line in scored[:limit]]


# --------------------------------------------------------------------- 意图


@dataclass
class Intent:
    """从一句中文问句中解析出的查询意图。"""

    text: str = ""
    city: Optional[City] = None
    city_mentions: List[str] = field(default_factory=list)
    from_text: str = ""
    to_text: str = ""
    mode: str = "now"
    datetime: Optional[str] = None
    fare: str = "ic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "city": self.city.name if self.city else None,
            "city_key": self.city.key if self.city else None,
            "city_mentions": self.city_mentions,
            "from": self.from_text,
            "to": self.to_text,
            "mode": self.mode,
            "datetime": self.datetime,
            "fare": self.fare,
        }


_FROM_TO_PATTERNS = [
    r"从\s*(?P<from>[^，,。；;？?！!]{1,32}?)\s*(?:到|去|至|->|→|―|—|~)\s*(?P<to>[^，,。；;？?！!]{1,32}?)"
    r"(?=$|[，,。；;？?！!]|怎么|如何|坐|乘|搭|要|需要|多久|多长时间|有多久|几点|票价|多少钱)",
    r"(?P<from>[^，,。；;？?！!]{1,32}?)\s*(?:到|去|至)\s*(?P<to>[^，,。；;？?！!]{1,32}?)"
    r"(?=$|[，,。；;？?！!]|怎么|如何|坐|乘|搭|要|需要|多久|多长时间|有多久|几点|票价|多少钱)",
]

_MODE_PATTERNS = [
    (r"首班|最早", "first"),
    (r"末班|最晚", "last"),
    (r"到达|几点到|最晚到", "arrive"),
    (r"出发|几点走", "depart"),
]

_TIME_RE = re.compile(r"(?P<date>\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)?\s*(?P<clock>\d{1,2}[:：]\d{2})")


def _clean_segment(text: str) -> str:
    text = text.strip()
    for stop in _STOPWORDS:
        text = text.replace(stop, "")
    return text.strip(" 的了吗呢啊把从到去坐乘")


def _strip_city(text: str, city_names: Iterable[str]) -> str:
    """从片段里去掉城市名（仅作为兜底变体，不破坏「北京南站」这类站名）。"""
    for name in city_names:
        if name and name in text:
            text = text.replace(name, "", 1)
    return text.strip(" 的了吗呢啊把从到去坐乘")


def parse_intent(text: str, cities: Sequence[City]) -> Intent:
    """解析中文问句。"""
    intent = Intent(text=text)

    for mode_keyword, mode in _MODE_PATTERNS:
        if re.search(mode_keyword, text):
            intent.mode = mode
            break

    if re.search(r"现金|付现|现金支付", text):
        intent.fare = "cash"
    elif re.search(r"交通卡|刷卡|一卡通|乘车码|ic卡", text):
        intent.fare = "ic"

    time_match = _TIME_RE.search(text)
    if time_match and time_match.group("clock"):
        clock = time_match.group("clock").replace("：", ":")
        date_part = (time_match.group("date") or "").strip()
        digits = re.sub(r"\D", "", date_part) if date_part else ""
        if len(digits) == 8:
            intent.datetime = f"{digits}{clock.replace(':', '')}"

    mentions = find_city_mentions(text, cities)
    intent.city_mentions = [city.name for _, city in mentions]
    if mentions:
        intent.city = mentions[0][1]

    for pattern in _FROM_TO_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue
        raw_from = match.group("from")
        raw_to = match.group("to")
        intent.from_text = _clean_segment(raw_from)
        intent.to_text = _clean_segment(raw_to)
        if intent.from_text or intent.to_text:
            break

    return intent


# --------------------------------------------------------------- 整句解析


@dataclass
class TripQuery:
    """一次完整出行查询的解析结果。"""

    intent: Intent
    city: Optional[City] = None
    from_matches: List[StationMatch] = field(default_factory=list)
    to_matches: List[StationMatch] = field(default_factory=list)
    from_text: str = ""
    to_text: str = ""

    @property
    def origin(self) -> Optional[Station]:
        return self.from_matches[0].station if self.from_matches else None

    @property
    def destination(self) -> Optional[Station]:
        return self.to_matches[0].station if self.to_matches else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "city": self.city.to_dict() if self.city else None,
            "from_text": self.from_text,
            "to_text": self.to_text,
            "from_candidates": [m.to_dict() for m in self.from_matches],
            "to_candidates": [m.to_dict() for m in self.to_matches],
        }


def _segment_variants(segment: str, city_names: Sequence[str]) -> List[str]:
    variants = [segment]
    stripped = _strip_city(segment, city_names)
    if stripped and stripped not in variants:
        variants.append(stripped)
    return variants


def _best_matches(
    segment: str,
    city_names: Sequence[str],
    stations: Sequence[Station],
    limit: int = 5,
) -> List[StationMatch]:
    """在多个片段变体中挑出最佳车站候选。"""
    best: List[StationMatch] = []
    best_score = -1.0
    for variant in _segment_variants(segment, city_names):
        matches = resolve_station(variant, stations, limit=limit)
        if not matches:
            continue
        if matches[0].score > best_score:
            best_score = matches[0].score
            best = matches
    return best


def resolve_trip(
    text: str,
    cities: Sequence[City],
    stations_provider,
    prefer_cities: Sequence[str] = (),
) -> TripQuery:
    """把一句中文问句解析成「城市 + 起点 + 终点」。

    ``stations_provider`` 需返回给定城市 key 的车站列表。
    """
    intent = parse_intent(text, cities)
    city_names = [city.name for _, city in find_city_mentions(text, cities)]
    query = TripQuery(intent=intent, from_text=intent.from_text, to_text=intent.to_text)
    if intent.city is not None:
        query.city = intent.city

    candidate_cities: List[City] = []
    if intent.city is not None:
        candidate_cities.append(intent.city)
    for name in prefer_cities:
        for city in cities:
            if city.name == name and city not in candidate_cities:
                candidate_cities.append(city)

    if not intent.from_text or not intent.to_text:
        return query

    best_city: Optional[City] = None
    best_from: List[StationMatch] = []
    best_to: List[StationMatch] = []
    best_score = -1.0

    for city in candidate_cities:
        stations = stations_provider(city.key)
        if not stations:
            continue
        from_matches = _best_matches(intent.from_text, city_names, stations)
        to_matches = _best_matches(intent.to_text, city_names, stations)
        if not from_matches or not to_matches:
            continue
        score = from_matches[0].score + to_matches[0].score
        if score > best_score:
            best_score = score
            best_city = city
            best_from = from_matches
            best_to = to_matches

    if best_city is not None:
        query.city = best_city
        query.from_matches = best_from
        query.to_matches = best_to
    return query
