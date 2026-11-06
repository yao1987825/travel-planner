"""12306 查票工具组 — train_store（自包含，零外部依赖）。

提供 2 个工具函数：
  train_query            — 直达票查询
  train_transfer_query   — 中转票查询

通过 ToolRegistry 动态加载，供主 Agent dispatch 调用。
所有辅助逻辑（车站查询、API 客户端）内联于此文件，无需额外模块。
"""

import json
import logging
import random
import re
import ssl
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Coroutine
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[dict], dict]

__all__ = ["train_query", "train_transfer_query", "main"]

# ═══════════════════════════════════════════════════════════════════
# 车站电报码查询（原 _station.py）
# ═══════════════════════════════════════════════════════════════════

_STATION_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
_CACHE_FILE = Path(__file__).parent.parent / "data" / "station_cache.json"

_station_map: dict[str, str] | None = None
_station_lock = threading.Lock()


def _load_station_cache() -> dict[str, str]:
    """从本地 JSON 缓存加载站名映射。"""
    if _CACHE_FILE.exists():
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _fetch_station_online() -> dict[str, str]:
    """从 12306 在线拉取站名映射。"""
    try:
        req = Request(
            _STATION_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TrainQuery/1.0)"},
        )
        with urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            text = resp.read().decode("utf-8")

        station_map: dict[str, str] = {}
        for item in text.split("@"):
            parts = item.split("|")
            if len(parts) >= 4:
                name, code = parts[1], parts[2]
                if name and code:
                    station_map[name] = code

        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(station_map, f, ensure_ascii=False)
        except OSError:
            pass
        return station_map
    except (URLError, OSError) as e:
        logger.warning("拉取车站数据失败: %s", e)
        return {}


def _get_station_code(name: str) -> str | None:
    """获取车站电报码，缓存未命中时尝试在线刷新（线程安全）。"""
    global _station_map
    with _station_lock:
        if _station_map is None:
            _station_map = _load_station_cache()
        code = _station_map.get(name)
        if code:
            return code
    # 在线刷新
    online = _fetch_station_online()
    if online:
        with _station_lock:
            _station_map.update(online)
        return _station_map.get(name)
    return None


# ═══════════════════════════════════════════════════════════════════
# 12306 API 客户端（原 _api.py）
# ═══════════════════════════════════════════════════════════════════

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ),
]

_DIRECT_URL = "https://kyfw.12306.cn/otn/leftTicket/query"
_DIRECT_INIT = "https://kyfw.12306.cn/otn/leftTicket/init"
_TRANSFER_INIT = "https://kyfw.12306.cn/otn/lcQuery/init"
_TRANSFER_BASE = "https://kyfw.12306.cn"
_MAX_RETRIES = 3

# NOTE: 12306 官方证书链在某些环境下不完整，导致 ssl.SSLCertVerificationError。
# 作为查询类公开 API，此处关闭证书校验是务实选择，非敏感数据传输。
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# 直达票 pipe-separated 字段索引
_FIELD_IDX = {
    "train_no": 2,
    "station_train_code": 3,
    "from_station_code": 6,
    "to_station_code": 7,
    "start_time": 8,
    "arrive_time": 9,
    "lishi": 10,
    "gr_num": 21,
    "rw_num": 23,
    "tz_num": 25,
    "yw_num": 28,
    "yz_num": 29,
    "ze_num": 30,
    "zy_num": 31,
    "swz_num": 32,
}

# 席别 key → 中文名
_SEAT_NAMES: dict[str, str] = {
    "swz_num": "商务座",
    "zy_num": "一等座",
    "ze_num": "二等座",
    "rw_num": "软卧",
    "yw_num": "硬卧",
    "yz_num": "硬座",
    "tz_num": "特等座",
    "gr_num": "高级软卧",
}

# 车次代号前缀 → 类型
_TRAIN_TYPE_MAP: list[tuple[str, str]] = [
    ("G", "高铁"),
    ("C", "高铁"),
    ("D", "动车"),
    ("Z", "直达"),
    ("T", "特快"),
    ("K", "快速"),
]


def _random_ua() -> str:
    """随机选一个 User-Agent。"""
    return random.choice(_USER_AGENTS)


def _http_get(url: str, timeout: int = 15) -> str:
    """发起 GET 请求，返回响应文本（自动处理 UTF-8 BOM）。"""
    req = Request(url, headers={"User-Agent": _random_ua()})
    with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read().decode("utf-8-sig")


def _classify_train(code: str) -> str:
    """根据车次代号判断类型。"""
    for prefix, label in _TRAIN_TYPE_MAP:
        if code.startswith(prefix):
            return label
    return "其他"


def _parse_seats(parts: list[str]) -> dict[str, str]:
    """从 pipe-separated 字段中提取有余票的席别。"""
    seats: dict[str, str] = {}
    for key, name in _SEAT_NAMES.items():
        idx = _FIELD_IDX[key]
        val = parts[idx] if idx < len(parts) else ""
        if val and val not in ("无", "", "--"):
            seats[name] = val
    return seats


# ── Cookie 管理（线程安全）───────────────────────────────────────

_direct_cookies: dict[str, str] = {}
_direct_cookie_lock = threading.Lock()


def _init_direct_cookies() -> None:
    """访问余票查询首页获取必要 Cookie。"""
    global _direct_cookies
    with _direct_cookie_lock:
        _direct_cookies = {}
    try:
        req = Request(_DIRECT_INIT, headers={"User-Agent": _random_ua()})
        with urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            for header in resp.headers.get_all("Set-Cookie") or []:
                parts = header.split(";")[0]
                if "=" in parts:
                    k, v = parts.split("=", 1)
                    with _direct_cookie_lock:
                        _direct_cookies[k.strip()] = v.strip()
    except (URLError, OSError) as e:
        logger.warning("获取直达查询Cookie失败: %s", e)


# ── 直达票查询 ────────────────────────────────────────────────


def _query_direct(
    train_date: str,
    from_code: str,
    to_code: str,
) -> list[dict[str, Any]]:
    """查询直达票，返回车次列表。"""
    params = {
        "leftTicketDTO.train_date": train_date,
        "leftTicketDTO.from_station": from_code,
        "leftTicketDTO.to_station": to_code,
        "purpose_codes": "ADULT",
    }
    url = f"{_DIRECT_URL}?{urlencode(params)}"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if attempt == 1 or not _direct_cookies:
                _init_direct_cookies()

            req = Request(url, headers={"User-Agent": _random_ua()})
            with _direct_cookie_lock:
                if _direct_cookies:
                    req.add_header(
                        "Cookie",
                        "; ".join(f"{k}={v}" for k, v in _direct_cookies.items()),
                    )
            with urlopen(req, timeout=15, context=_SSL_CTX) as resp:
                text = resp.read().decode("utf-8-sig").strip()

            if not text.startswith("{"):
                preview = text[:500] if text else "(空内容)"
                logger.warning("直达查询返回非JSON(疑似IP限制)，第%d次重试，前500字符: %s", attempt, preview)
                with _direct_cookie_lock:
                    _direct_cookies.clear()
                # 指数退避：1→2→4秒，避免频繁触发限制
                backoff = random.uniform(2 ** attempt, 2 ** (attempt + 1))
                logger.info("等待 %.1f 秒后重试...", backoff)
                time.sleep(backoff)
                continue

            body = json.loads(text)
            if not body.get("status"):
                msgs = body.get("messages", ["未知错误"])
                logger.warning("直达查询返回错误: %s", msgs)
                return []

            result_list = body.get("data", {}).get("result", [])
            return [_parse_direct_item(item) for item in result_list]

        except (URLError, OSError) as e:
            logger.warning("直达查询失败 (第%d次): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(random.uniform(1, 2))
        except (ValueError, KeyError) as e:
            logger.error("直达查询解析失败: %s", e)
            return []

    return []


def _parse_direct_item(raw: str) -> dict[str, Any]:
    """解析单条直达票记录。"""
    parts = raw.split("|")
    result: dict[str, Any] = {}
    for field, idx in _FIELD_IDX.items():
        result[field] = parts[idx] if idx < len(parts) else ""

    code = result.get("station_train_code", "")
    result["train_type"] = _classify_train(code)
    result["seats"] = _parse_seats(parts)
    result["has_ticket"] = bool(result["seats"])
    return result


# ── 中转票查询 ────────────────────────────────────────────────

_transfer_cookies: dict[str, str] = {}
_transfer_cookie_lock = threading.Lock()


def _http_get_transfer(url: str, timeout: int = 15) -> str:
    """带 Cookie 的 GET 请求，自动保存和发送 Cookie（线程安全）。"""
    req = Request(url, headers={"User-Agent": _random_ua()})
    with _transfer_cookie_lock:
        if _transfer_cookies:
            req.add_header(
                "Cookie",
                "; ".join(f"{k}={v}" for k, v in _transfer_cookies.items()),
            )
    with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        for header in resp.headers.get_all("Set-Cookie") or []:
            parts = header.split(";")[0]
            if "=" in parts:
                k, v = parts.split("=", 1)
                with _transfer_cookie_lock:
                    _transfer_cookies[k.strip()] = v.strip()
        return resp.read().decode("utf-8")


def _query_transfer(
    train_date: str,
    from_code: str,
    to_code: str,
    middle_code: str = "",
) -> list[dict[str, Any]]:
    """查询中转票，返回中转方案列表。"""
    global _transfer_cookies
    with _transfer_cookie_lock:
        _transfer_cookies = {}

    # 初始化获取动态查询路径
    search_url = "/lcquery/queryU"
    try:
        init_text = _http_get_transfer(_TRANSFER_INIT)
        match = re.search(r"var\s+lc_search_url\s*=\s*'(.+?)'", init_text)
        if match:
            search_url = match.group(1)
    except (URLError, OSError) as e:
        logger.warning("中转初始化失败: %s", e)

    params = {
        "train_date": train_date,
        "from_station_telecode": from_code,
        "to_station_telecode": to_code,
        "middle_station": middle_code,
        "result_index": 0,
        "can_query": "Y",
        "isShowWZ": "N",
        "purpose_codes": "00",
        "channel": "E",
    }
    url = f"{_TRANSFER_BASE}{search_url}?{urlencode(params)}"

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            text = _http_get_transfer(url)
            body = json.loads(text)

            if not body.get("status"):
                logger.warning("中转查询返回错误")
                return []

            data = body.get("data")
            if not isinstance(data, dict):
                return []
            return data.get("middleList", [])

        except (URLError, OSError) as e:
            logger.warning("中转查询失败 (第%d次): %s", attempt, e)
            if attempt < _MAX_RETRIES:
                time.sleep(random.uniform(2, 4))
                with _transfer_cookie_lock:
                    _transfer_cookies = {}
                try:
                    init_text = _http_get_transfer(_TRANSFER_INIT)
                    match = re.search(
                        r"var\s+lc_search_url\s*=\s*'(.+?)'", init_text
                    )
                    if match:
                        search_url = match.group(1)
                    url = f"{_TRANSFER_BASE}{search_url}?{urlencode(params)}"
                except (URLError, OSError):
                    pass
        except (ValueError, KeyError) as e:
            logger.error("中转查询解析失败: %s", e)
            return []

    return []


# ═══════════════════════════════════════════════════════════════════
# 日期解析
# ═══════════════════════════════════════════════════════════════════


def _resolve_date(date_str: str) -> str:
    """将自然语言日期转换为 YYYY-MM-DD 格式。

    支持：今天/明天/后天/大后天、YYYY-MM-DD、M月D日。
    """
    if not date_str:
        return ""
    today = date.today()
    relative = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
    if date_str in relative:
        return (today + timedelta(days=relative[date_str])).isoformat()
    try:
        return date.fromisoformat(date_str).isoformat()
    except ValueError:
        pass
    m = re.match(r"(\d{1,2})月(\d{1,2})[日号]", date_str)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            return date(today.year, month, day).isoformat()
        except ValueError:
            pass
    return date_str


# ═══════════════════════════════════════════════════════════════════
# 工具定义（OpenAI Function Calling 格式）
# ═══════════════════════════════════════════════════════════════════

DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "train_query",
            "description": (
                "查询火车直达票。返回指定日期、出发站到到达站的所有直达车次及余票。"
                "支持按车次类型（高铁/动车/特快等）过滤。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": (
                            "出发日期，支持：YYYY-MM-DD、明天、后天、大后天、M月D日"
                        ),
                    },
                    "from_station": {
                        "type": "string",
                        "description": "出发站名称，如'北京'、'上海虹桥'",
                    },
                    "to_station": {
                        "type": "string",
                        "description": "到达站名称，如'深圳北'、'成都东'",
                    },
                    "train_type": {
                        "type": "string",
                        "description": "车次类型过滤：高铁、动车、直达、特快、快速。不传不过滤",
                    },
                },
                "required": ["date", "from_station", "to_station"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "train_transfer_query",
            "description": (
                "查询火车中转票。当直达票售罄或无直达车次时查询中转方案。"
                "可指定中转站，不指定则自动推荐。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "出发日期，支持：YYYY-MM-DD、明天、后天、大后天、M月D日",
                    },
                    "from_station": {
                        "type": "string",
                        "description": "出发站名称",
                    },
                    "to_station": {
                        "type": "string",
                        "description": "到达站名称",
                    },
                    "middle_station": {
                        "type": "string",
                        "description": "中转站名称，不传则自动推荐",
                    },
                },
                "required": ["date", "from_station", "to_station"],
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════
# Executor 实现
# ═══════════════════════════════════════════════════════════════════


def train_query(args: dict) -> dict:
    """查询直达票。"""
    date_str = _resolve_date(args.get("date", ""))
    from_name = args.get("from_station", "")
    to_name = args.get("to_station", "")
    train_type = args.get("train_type", "")

    if not date_str:
        return {"error": "请提供出发日期"}

    from_code = _get_station_code(from_name)
    to_code = _get_station_code(to_name)

    if not from_code:
        return {"error": f"未找到车站: {from_name}"}
    if not to_code:
        return {"error": f"未找到车站: {to_name}"}

    results = _query_direct(date_str, from_code, to_code)

    if train_type:
        results = [r for r in results if r.get("train_type") == train_type]

    has_ticket = [r for r in results if r.get("has_ticket")]
    sold_out = [r for r in results if not r.get("has_ticket")]

    return {
        "trip_date": date_str,
        "depart_station": from_name,
        "arrive_station": to_name,
        "train_count": len(results),
        "ticket_count": len(has_ticket),
        "soldout_count": len(sold_out),
        "has_ticket_trains": has_ticket[:10],
        "sold_out_trains": sold_out[:10],
    }


def train_transfer_query(args: dict) -> dict:
    """查询中转票。"""
    date_str = _resolve_date(args.get("date", ""))
    from_name = args.get("from_station", "")
    to_name = args.get("to_station", "")
    middle_name = args.get("middle_station", "")

    if not date_str:
        return {"error": "请提供出发日期"}

    from_code = _get_station_code(from_name)
    to_code = _get_station_code(to_name)
    middle_code = _get_station_code(middle_name) if middle_name else ""

    if not from_code:
        return {"error": f"未找到车站: {from_name}"}
    if not to_code:
        return {"error": f"未找到车站: {to_name}"}

    raw = _query_transfer(date_str, from_code, to_code, middle_code)

    routes = []
    for item in raw[:5]:
        trains = item.get("fullList", [])
        if len(trains) < 2:
            continue
        first, second = trains[0], trains[1]
        routes.append(
            {
                "middle": item.get("middle_station_name", ""),
                "total_duration": item.get("all_lishi", ""),
                "wait_time": item.get("wait_time", ""),
                "first_train": first.get("station_train_code", ""),
                "first_from": first.get("from_station_name", ""),
                "first_start": first.get("start_time", ""),
                "first_to": first.get("to_station_name", ""),
                "first_arrive": first.get("arrive_time", ""),
                "second_train": second.get("station_train_code", ""),
                "second_from": second.get("from_station_name", ""),
                "second_start": second.get("start_time", ""),
                "second_to": second.get("to_station_name", ""),
                "second_arrive": second.get("arrive_time", ""),
            }
        )

    return {
        "trip_date": date_str,
        "depart_station": from_name,
        "arrive_station": to_name,
        "route_count": len(raw),
        "routes": routes,
    }


# ═══════════════════════════════════════════════════════════════════
# Executor 注册表
# ═══════════════════════════════════════════════════════════════════

EXECUTORS: dict[str, ToolExecutor] = {
    "train_query": train_query,
    "train_transfer_query": train_transfer_query,
}


# ═══════════════════════════════════════════════════════════════════
# Dispatch
# ═══════════════════════════════════════════════════════════════════

_ACTION_TO_TOOL: dict[str, str] = {
    "query": "train_query",
    "transfer_query": "train_transfer_query",
}


async def train_dispatch(
    params: dict,
    execute_fn: Callable[[str, dict], Coroutine[Any, Any, str]],
) -> dict:
    """12306 查票结构化分发。"""
    action = params.get("action", "query")
    tool_name = _ACTION_TO_TOOL.get(action)

    if not tool_name:
        return {
            "reply": f"未知操作: {action}",
            "metadata": {"action": action, "error": "unknown_action"},
            "status": "failed",
        }

    tool_args = {k: v for k, v in params.items() if k != "action"}
    result_str = await execute_fn(tool_name, tool_args)
    result = json.loads(result_str) if result_str else {}

    is_failed = isinstance(result, dict) and bool(result.get("error"))
    reply = _format_reply(action, result, is_failed)

    return {
        "reply": reply,
        "metadata": result,
        "status": "failed" if is_failed else "success",
    }


def _format_reply(action: str, result: dict, is_failed: bool) -> str:
    """根据 action 类型格式化语音播报友好回复。"""
    if is_failed:
        return result.get("error", "查询失败，请稍后再试")
    formatter = _REPLY_FORMATTERS.get(action)
    if formatter:
        return formatter(result)
    return str(result)


# ── 回复格式化策略 ──────────────────────────────────────────


def _format_query(r: dict) -> str:
    """直达票查询回复。"""
    total = r.get("total", 0)
    has_count = r.get("has_ticket_count", 0)
    sold_count = r.get("sold_out_count", 0)
    trains = r.get("trains", [])
    from_name = r.get("from", "")
    to_name = r.get("to", "")
    d = r.get("date", "")

    if total == 0:
        return f"{d} {from_name}到{to_name}没有直达车次，要不要帮您查一下中转方案？"

    parts = [f"{d} {from_name}到{to_name}共{total}趟直达车次"]
    if sold_count > 0:
        parts.append(f"其中{has_count}趟有票，{sold_count}趟已售罄")
    else:
        parts.append("全部有票")

    if trains:
        parts.append("有票车次：")
        for t in trains[:5]:
            code = t.get("station_train_code", "")
            start = t.get("start_time", "")
            arrive = t.get("arrive_time", "")
            duration = t.get("lishi", "")
            seats = t.get("seats", {})
            seat_str = "、".join(f"{k}{v}" for k, v in seats.items())
            parts.append(f"{code} {start}发车{arrive}到，历时{duration}，{seat_str}")

    return "。".join(parts)


def _format_transfer(r: dict) -> str:
    """中转票查询回复。"""
    routes = r.get("routes", [])
    from_name = r.get("from", "")
    to_name = r.get("to", "")
    d = r.get("date", "")

    if not routes:
        return f"{d} {from_name}到{to_name}没有找到中转方案"

    total = r.get("total", 0)
    parts = [
        f"{d} {from_name}到{to_name}共找到{total}个中转方案，"
        f"为您展示前{len(routes)}个"
    ]

    for i, route in enumerate(routes, 1):
        mid = route.get("middle", "")
        dur = route.get("total_duration", "")
        wait = route.get("wait_time", "")
        f1 = route.get("first_train", "")
        f1s = route.get("first_start", "")
        f1a = route.get("first_arrive", "")
        f2 = route.get("second_train", "")
        f2s = route.get("second_start", "")
        f2a = route.get("second_arrive", "")

        parts.append(
            f"方案{i}，经{mid}中转，总耗时{dur}，等待{wait}。"
            f"第一程{f1}，{f1s}出发，{f1a}到{mid}。"
            f"第二程{f2}，{f2s}从{mid}出发，{f2a}到达"
        )

    return "。".join(parts)


_REPLY_FORMATTERS: dict[str, Callable[[dict], str]] = {
    "query": _format_query,
    "transfer_query": _format_transfer,
}


def main(date: str = "", from_station: str = "", to_station: str = "",
         train_type: str = "", middle_station: str = "",
         action: str = "query") -> dict:
    """Dify Code 节点入口函数。"""
    args = {"date": date, "from_station": from_station, "to_station": to_station,
            "train_type": train_type, "middle_station": middle_station}
    if action == "transfer_query":
        result = train_transfer_query(args)
    else:
        result = train_query(args)
    return {"result": json.dumps(result, ensure_ascii=False)}