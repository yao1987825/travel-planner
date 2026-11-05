#!/usr/bin/env python3
"""
bus_query.py —— 公交实时查询统一入口

把两个数据源的差异全包在这个脚本里, 上层(AI 或 shell)只需要记一条命令:

    python3 bus_query.py <子命令> [参数...]

为什么要有这个脚本(而不是让 AI 每次自己拼 curl):
  1. 掌上公交的 Origin 头带不带尾斜杠, 结果是「完整 JSON」和「47 字节占位串」的区别 ——
     手拼一次错一次, 脚本里写死就不会错。
  2. 到站预测要两跳: 先 CMD=103 拿线路站表(站序), 再用站序去请求 CMD=104 的
     STATIONORDER 参数 —— 中间还要做站名匹配和方向判定, 手拼很容易漏。
  3. 车来了的响应包着 **YGKJ 壳, 实时车辆是 AES-ECB 加密的, 还要先算 MD5 签名。
     这些细节不应该让模型每次现推。
  4. 线路目录(CMD=119)单个城市 300KB+, 直接读进上下文会炸 —— 脚本内部处理, 只吐需要的。

只用 Python 标准库, 不装任何第三方包(镜像里 python 是裸装的)。

子命令:
    lines    <城市>                    列线路目录
    live     <城市> <线路> [--dir 1|2] [--to <站名>]
    station  <城市> <站名>             查站点经过哪些线路
    route    <城市> <起点站> <终点站>   查直达线路(交集 + 方向校验)
    scan     <城市> [--limit N]        全城扫: 哪些线路此刻有车
    cities   [--src mygolbs|chelaile]  列出数据源覆盖的城市

通用选项:
    --src mygolbs|chelaile   强制数据源(默认: 掌上公交优先, 没有再退车来了)
    --json                   输出原始 JSON(给脚本用), 默认输出人话摘要
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(HERE), "references")

# 默认城市: 郴州。改这里 + SKILL.md 里的说明。
DEFAULT_CITY = os.environ.get("BUS_DEFAULT_CITY", "郴州市")

UA_MG = "Mozilla/5.0 (Linux; Android 12) Mobile Safari/537.36"
UA_CL = "Mozilla/5.0 (Linux; Android 13) Mobile MicroMessenger/8.0"

MG_URL = "https://h5.mygolbs.com/ApiData.do"
CL_URL = "https://web.chelaile.net.cn/api/"
CL_COMMON = "s=h5&v=9.1.2&vc=1&sign=1&userId=&h5Id=&src=app"

# 车来了实时车辆接口的加密参数(上游固定值)
CL_SALT = "qwihrnbtmj"
# 密钥是 32 个字符的 UTF-8 字节(AES-256), 不是 hex —— 见 aes_ecb_decrypt 的注释
CL_AES_KEY = b"422556651C7F7B2B5C266EED06068230"


# ---------------------------------------------------------------- 工具函数

def die(msg, code=1):
    print(f"[bus] 错误: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json_ref(name, default=None):
    path = os.path.join(REFS, name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default if default is not None else {}


def http(url, data=None, headers=None, timeout=25):
    """发一个 HTTP 请求, 返回 (status, body_bytes)。"""
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


# ---------------------------------------------------------------- 城市归一化

def normalize_city(raw):
    """把用户写的城市名归一成数据源认的名字。

    '郴州' → '郴州市'; '桂阳' → 查 districts.json → '郴州市';
    '深圳市' → '深圳市'(不变)。

    districts.json 的键是官方全名('桂阳县'), 用户往往只写'桂阳' ——
    所以带常见后缀再试一遍。映射出来的值还要校验确实是座城市,
    否则像"万宁市 → 省直辖县级行政区划"这种会直接把查询带沟里。
    """
    if not raw:
        return DEFAULT_CITY
    name = raw.strip()
    bare = re.sub(r"(市|特别行政区|自治州|地区|盟)$", "", name)
    districts = load_json_ref("districts.json", {})
    known = mygolbs_cities() | set(chelaile_cities().keys())

    # 区县 → 地级市
    for cand in (name, bare, bare + "县", bare + "区", bare + "市", bare + "旗"):
        if cand and cand in districts:
            mapped = districts[cand]
            if mapped in known or mapped.endswith(("市", "州", "盟", "地区")):
                return mapped
    # 已经是"XX市"就原样用
    if name.endswith(("市", "县", "区")):
        return name
    return name + "市"


def mygolbs_cities():
    """掌上公交支持的城市名集合(离线缓存, 来自 CMD=101)。"""
    data = load_json_ref("mygolbs_cities.json", [])
    return set(data)


def chelaile_cities():
    """车来了城市 ID 映射: {"郴州市": "212"}。"""
    return load_json_ref("bus_cities.json", {})


# ---------------------------------------------------------------- 掌上公交

def mg_call(cmd, **params):
    """调掌上公交接口。cmd 是 CMD 的值(如 '104'), 其余参数平铺。

    Origin 头必须原样是 'https://h5.mygolbs.com'(无尾斜杠) ——
    带尾斜杠/换 http/不带, 上游都回 HTTP 200 + 47 字节占位串, 症状是"永远查不到"。
    """
    headers = {
        "Origin": "https://h5.mygolbs.com",
        "Referer": "https://h5.mygolbs.com/",
        "User-Agent": UA_MG,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {"CMD": cmd}
    payload.update(params)
    body = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        _, raw = http(MG_URL, data=body, headers=headers)
    except urllib.error.HTTPError as exc:
        die(f"掌上公交返回 HTTP {exc.code}(线路名不存在或缺 CITYNAME 时会回错误页)")
    except urllib.error.URLError as exc:
        die(f"连不上掌上公交: {exc.reason}")
    text = raw.decode("utf-8", "replace")
    # 占位串不是 JSON, 直接判掉
    if not text.lstrip().startswith("{"):
        die(f"掌上公交返回的不是 JSON(检查 Origin 头): {text[:80]!r}")
    try:
        return json.loads(text)
    except ValueError:
        die(f"掌上公交返回的不是合法 JSON: {text[:120]!r}")


def mg_lines(city):
    """城市线路目录 → {线路名: [方向1记录, 方向2记录]}"""
    data = mg_call("119", CITYNAME=city)
    # status 有时是数字 1, 有时是字符串 "1" —— 统一按字符串比
    if str(data.get("status")) != "1":
        return {}
    out = {}
    for b in data.get("buslines") or []:
        name = (b.get("lineName") or "").strip()
        if not name:
            continue
        out.setdefault(name, {})[str(b.get("upperOrDown") or "1")] = b
    return out


def mg_stations(city, line, direction="1"):
    """线路站表(CMD=103) → [{stationName, stationOrder, ...}]"""
    data = mg_call("103", CITYNAME=city, LINENAME=line, DIRECTION=direction)
    if data.get("status") not in ("1", 1):
        return []
    return data.get("data") or []


def mg_live(city, line, direction="1", station_order=None):
    """实时车辆(CMD=104)。给了 station_order 就附带到站预测。"""
    params = {"CMD": "104", "CITYNAME": city, "LINENAME": line, "DIRECTION": direction}
    if station_order:
        params["STATIONORDER"] = str(station_order)
    return mg_call("104", **params)


def mg_station_search(city, keyword):
    """站点搜索(CMD=102) → [站点记录]"""
    data = mg_call("102", CITYNAME=city, KEYWORD=keyword)
    return data.get("busstations") or []


# ---------------------------------------------------------------- 车来了

def cl_call(path, **params):
    """调车来了接口。响应裹着 **YGKJ 壳, 先剥壳再解析。"""
    query = CL_COMMON + "".join(f"&{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    headers = {"Referer": "https://web.chelaile.net.cn/customer_ch5/", "User-Agent": UA_CL}
    try:
        _, raw = http(CL_URL + path + "?" + query, headers=headers)
    except urllib.error.HTTPError as exc:
        die(f"车来了返回 HTTP {exc.code}")
    except urllib.error.URLError as exc:
        die(f"连不上车来了: {exc.reason}")
    text = raw.decode("utf-8", "replace")
    if "**YGKJ" in text:
        text = text.split("**YGKJ", 1)[1].rsplit("YGKJ##", 1)[0]
    try:
        payload = json.loads(text)
    except ValueError:
        die(f"车来了返回的不是合法 JSON: {text[:120]!r}")
    return payload.get("jsonr") or {}


def cl_lines(city):
    """车来了线路目录 → {线路名: [记录...]}"""
    cid = chelaile_cities().get(city)
    if not cid:
        return {}
    jr = cl_call("bus/cityLineList", cityId=cid)
    if jr.get("status") != "00":
        return {}
    all_lines = ((jr.get("data") or {}).get("allLines") or {}).get("all") or []
    out = {}
    for x in all_lines:
        out.setdefault(str(x.get("lineName") or ""), []).append(x)
    return out


def cl_route(line_id, city):
    """车来了线路站表 → [{sn, order, lat, lng, distanceToSp}]"""
    cid = chelaile_cities().get(city)
    if not cid:
        return []
    jr = cl_call("bus/line!lineRoute.action", cityId=cid, lineId=line_id)
    if jr.get("status") != "00":
        return []
    return ((jr.get("data") or {}).get("stations")) or []


def cl_live(line_id, city, target=None, line_name=None, direction=0, line_no=None):
    """车来了实时车辆(响应 AES-ECB 加密, 解完才有 JSON)。

    target: (站名, 下一站名, 目标站序)。给了才有"到站预测"。
    签名对**参数顺序**敏感 —— 必须按前端顺序拼:
        lineId=…&lineName=…&direction=…&stationName=…&nextStationName=…&lineNo=…&targetOrder=…
    末尾拼盐值 qwihrnbtmj, 取 MD5(小写)。
    """
    cid = chelaile_cities().get(city)
    if not cid:
        return {}
    params = {"cityId": cid, "lineId": line_id}
    if target:
        station_name, next_name, target_order = target
        params.update({
            "lineName": line_name, "direction": direction,
            "stationName": station_name, "nextStationName": next_name,
            "targetOrder": target_order,
        })
        sign_src = "&".join([
            f"lineId={line_id}", f"lineName={line_name}", f"direction={direction}",
            f"stationName={station_name}", f"nextStationName={next_name}",
            f"lineNo={line_no}", f"targetOrder={target_order}",
        ]) + CL_SALT
    else:
        sign_src = f"lineId={line_id}" + CL_SALT
    params["cryptoSign"] = hashlib.md5(sign_src.encode("utf-8")).hexdigest()
    jr = cl_call("bus/line!encryptedLineDetail.action", **params)
    if jr.get("status") != "00":
        return {}
    data = jr.get("data") or {}
    enc = data.get("encryptResult")
    if not enc:
        return {}
    plain = aes_ecb_decrypt(base64.b64decode(enc), CL_AES_KEY)
    try:
        return json.loads(plain)
    except ValueError:
        return {}


# ---------------------------------------------------------------- AES-ECB

# 纯 Python 的 AES ECB 解密 —— 车来了的实时车辆接口用它加密。
# 不写这个就得依赖 cryptography / pycryptodome, 镜像里两个都没有。
_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a = (a ^ 0x1B) & 0xFF
    return a


def _mul(a, b):
    """GF(2^8) 乘法。"""
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r


def _key_expansion(key):
    """AES 密钥扩展 → 每轮一个轮密钥。支持 128/192/256 位。"""
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return [bytes(b for word in w[4 * r:4 * r + 4] for b in word) for r in range(nr + 1)]


def _inv_shift_rows(state):
    out = list(state)
    for r in range(1, 4):
        row = state[r:16:4]
        row = row[-r:] + row[:-r]
        for c in range(4):
            out[r + 4 * c] = row[c]
    return out


def _inv_mix_columns(state):
    out = list(state)
    for c in range(4):
        a = state[4 * c:4 * c + 4]
        out[4 * c + 0] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
        out[4 * c + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
        out[4 * c + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
        out[4 * c + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
    return out


def _add_round_key(state, rk):
    return [state[i] ^ rk[i] for i in range(16)]


def aes_ecb_decrypt(ciphertext, key):
    """AES ECB 解密 + PKCS7 去填充, 返回 bytes。

    车来了的实时车辆接口就是这个加密方式。

    ⚠️ 密钥用法有个坑: 文档里写"密钥: 422556651C7F7B2B5C266EED06068230(hex)",
    但上游 JS 实际是 `CryptoJS.enc.Utf8.parse(...)` —— 也就是把这 32 个字符
    当 **UTF-8 字符串字节** 用, 即 **AES-256**(32 字节密钥), 不是 hex 解成
    16 字节的 AES-128。用错会解出一堆乱码。
    """
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key 必须是 16/24/32 字节")
    if len(ciphertext) % 16 != 0:
        raise ValueError("密文长度必须是 16 的倍数")
    rks = _key_expansion(key)
    nr = len(rks) - 1
    out = bytearray()
    for off in range(0, len(ciphertext), 16):
        block = list(ciphertext[off:off + 16])
        state = _add_round_key(block, rks[nr])
        for rnd in range(nr - 1, 0, -1):
            state = _inv_shift_rows(state)
            state = [_INV_SBOX[b] for b in state]
            state = _add_round_key(state, rks[rnd])
            state = _inv_mix_columns(state)
        state = _inv_shift_rows(state)
        state = [_INV_SBOX[b] for b in state]
        state = _add_round_key(state, rks[0])
        out.extend(state)
    # PKCS7 去填充
    pad = out[-1]
    if 1 <= pad <= 16 and len(out) >= pad:
        out = out[:-pad]
    return bytes(out)


# ---------------------------------------------------------------- 业务逻辑

def pick_source(city, forced=None):
    """决定用哪个数据源。返回 'mygolbs' / 'chelaile' / None。"""
    if forced:
        return forced
    if city in mygolbs_cities():
        return "mygolbs"
    if city in chelaile_cities():
        return "chelaile"
    # 离线缓存里没有, 实时问一次掌上公交的城市列表
    try:
        data = mg_call("101")
        names = {d.get("cityname") for d in (data.get("data") or [])}
        if city in names:
            return "mygolbs"
    except SystemExit:
        pass
    if city in chelaile_cities():
        return "chelaile"
    return None


def match_station(stations, name):
    """在站表里找目标站。支持精确 / 包含 / 去空格。"""
    if not name:
        return None
    target = name.strip()
    for st in stations:
        if st.get("stationName") == target:
            return st
    for st in stations:
        if st.get("stationName", "").startswith(target):
            return st
    for st in stations:
        if target in st.get("stationName", ""):
            return st
    # 车来了的字段叫 sn
    for st in stations:
        if st.get("sn") == target:
            return st
    return None


def order_of(station):
    """取站序: 掌上公交用 stationOrder, 车来了用 order。"""
    for key in ("stationOrder", "order", "index"):
        v = station.get(key)
        if v:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return None


def cmd_lines(args):
    city = normalize_city(args.city)
    src = pick_source(city, args.src)
    if not src:
        die(f"两个数据源都没覆盖「{city}」")
    out = {"city": city, "source": src, "lines": []}
    if src == "mygolbs":
        for name, dirs in sorted(mg_lines(city).items()):
            for direction, rec in sorted(dirs.items()):
                out["lines"].append({
                    "lineName": name,
                    "direction": direction,
                    "from": rec.get("from"),
                    "to": rec.get("to"),
                    "company": rec.get("company"),
                })
    else:
        for name, recs in sorted(cl_lines(city).items()):
            for rec in recs:
                out["lines"].append({
                    "lineName": name,
                    "lineId": rec.get("lineId"),
                    "from": rec.get("startStopName"),
                    "to": rec.get("endStopName"),
                    "firstTime": rec.get("firstTime"),
                    "lastTime": rec.get("lastTime"),
                })
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"城市: {city}   数据源: {src}   线路方向数: {len(out['lines'])}")
    for x in out["lines"][:args.limit]:
        extra = ""
        if x.get("firstTime"):
            extra = f"  首班 {x['firstTime']} 末班 {x.get('lastTime')}"
        print(f"  {x['lineName']:<12} 方向{x['direction'] if 'direction' in x else '-'}  "
              f"{x.get('from')} → {x.get('to')}{extra}")
    if len(out["lines"]) > args.limit:
        print(f"  ... 共 {len(out['lines'])} 条, 只显示前 {args.limit} 条")
    return 0


def cmd_live(args):
    city = normalize_city(args.city)
    src = pick_source(city, args.src)
    if not src:
        die(f"两个数据源都没覆盖「{city}」")

    line = args.line.strip()
    target_station = args.to

    if src == "mygolbs":
        catalog = mg_lines(city)
        # 车来了的线路名不带"路", 掌上公交带 —— 统一一下
        candidates = [line, line + "路"] if not line.endswith("路") else [line]
        rec = None
        for c in candidates:
            if c in catalog:
                rec = c
                break
        if rec is None:
            die(f"掌上公交没有「{line}」这条线路(该城共 {len(catalog)} 条)")
        line = rec
        dirs = catalog[line]
        direction = args.direction
        if not direction:
            # 没指定方向就默认 1(上行); 如果用户给了目标站, 再按站表纠正方向
            direction = "1" if "1" in dirs else next(iter(dirs))
        stations = mg_stations(city, line, direction)
        order = None
        if target_station:
            st = match_station(stations, target_station)
            if st is None:
                other = mg_stations(city, line, "2" if direction == "1" else "1")
                st = match_station(other, target_station)
                if st is not None:
                    direction = "2" if direction == "1" else "1"
                    stations = other
            if st is None:
                die(f"「{target_station}」不在这条线的站表里"
                    f"(站表: {', '.join(s.get('stationName', '') for s in stations[:8])} ...)")
            order = order_of(st)
        data = mg_live(city, line, direction, order)
        buses = data.get("list") or []
        predictions = data.get("routeOnStationRTimeInfoList") or []
        rec = (catalog.get(line) or {}).get(direction) or {}
        result = {
            "city": city, "source": "mygolbs", "line": line, "direction": direction,
            "from": rec.get("from"), "to": rec.get("to"),
            "hasReal": data.get("hasReal"),
            "planTime": data.get("planTime"),
            "buses": [
                {
                    "busNumber": b.get("busNumber"),
                    "nextStation": b.get("stationName"),
                    "distanceToNextStation": b.get("busToStationNiheDistance"),
                    "statusType": b.get("statusType"),
                } for b in buses
            ],
            "predictions": [
                {
                    "station": p.get("stationName"),
                    "busNumber": p.get("busNumber"),
                    "minutes": p.get("busToStationTime"),
                    "minutesText": p.get("busToStationTimeTips"),
                    "stopsAway": p.get("busToStationCount"),
                    "stopsText": p.get("busToStationTips"),
                    "distanceMeters": p.get("busToStationDistance"),
                    "distanceText": p.get("busToStationDistanceTips"),
                    "busNextStation": p.get("busToStationName"),
                } for p in predictions
            ],
        }
    else:
        catalog = cl_lines(city)
        candidates = [line, line.rstrip("路")]
        picked = None
        for c in candidates:
            if c in catalog:
                picked = c
                break
        if picked is None:
            die(f"车来了没有「{line}」这条线路(该城共 {len(catalog)} 条)")
        line = picked
        recs = catalog[line]
        line_id = recs[0].get("lineId")
        stations = cl_route(line_id, city)
        order = None
        target_info = None
        if target_station:
            st = match_station(stations, target_station)
            if st is None:
                die(f"「{target_station}」不在这条线的站表里")
            order = order_of(st)
            # 下一站名 —— 签名参数里要用
            idx = next((i for i, s in enumerate(stations)
                        if (s.get("sn") or "") == (st.get("sn") or "")), None)
            next_name = ""
            if idx is not None and idx + 1 < len(stations):
                next_name = stations[idx + 1].get("sn") or ""
            target_info = (st.get("sn") or target_station, next_name, order)

        detail = cl_live(line_id, city)
        line_info = detail.get("line") or {}
        if target_info:
            # 带目标站再查一次 —— 不带 targetOrder, 上游只给"到终点站"的预测
            detail2 = cl_live(
                line_id, city,
                target=target_info,
                line_name=line_info.get("name") or line,
                direction=line_info.get("direction", 0),
                line_no=line_info.get("lineNo", ""),
            )
            if detail2:
                detail = detail2
        buses = detail.get("buses") or []
        tip_desc = (detail.get("tip") or {}).get("desc")
        result = {
            "city": city, "source": "chelaile", "line": line,
            "lineId": line_id,
            "direction": line_info.get("direction"),
            "from": line_info.get("startSn"),
            "to": line_info.get("endSn"),
            "state": line_info.get("desc") or None,
            "price": line_info.get("price"),
            "firstTime": line_info.get("firstTime") or recs[0].get("firstTime"),
            "lastTime": line_info.get("lastTime") or recs[0].get("lastTime"),
            "tip": tip_desc,
            "buses": [
                {
                    "busNumber": b.get("licence") or b.get("busId"),
                    "nextStation": (stations[b.get("order", 1) - 1].get("sn")
                                    if isinstance(b.get("order"), int)
                                    and 0 < b.get("order", 0) <= len(stations) else None),
                    "stationOrder": b.get("order"),
                    "distanceToNextStation": b.get("distanceToWaitStn"),
                    "delay": b.get("delay"),
                } for b in buses
            ],
            "predictions": [],
        }
        # 到站预测: 每辆车的 travels[] 里有预计到站时刻
        for b in buses:
            for t in (b.get("travels") or []):
                arrives = t.get("arrivalTime")
                minutes = None
                if isinstance(arrives, (int, float)) and arrives > 0:
                    minutes = max(0, round((arrives / 1000.0 - time.time()) / 60.0))
                if minutes is None and not t.get("recommTip"):
                    continue
                result["predictions"].append({
                    "station": target_station or (detail.get("specialTargetOrder") and None),
                    "busNumber": b.get("licence") or b.get("busId"),
                    "minutes": minutes,
                    "minutesText": f"{minutes}分钟" if minutes is not None else None,
                    "arriveAt": t.get("recommTip"),
                    "distanceMeters": t.get("distance"),
                    "stopsAway": (order - b.get("order") + 1
                                  if order and isinstance(b.get("order"), int) else None),
                })

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"{result['city']}  {result['line']}  方向 {result.get('direction', '-')}  "
          f"(数据源 {result['source']})")
    if result.get("from") or result.get("to"):
        print(f"  走向: {result.get('from')} → {result.get('to')}")
    if result.get("hasReal") == "0":
        print("  ⚠ 上游不给该城实时车辆位置(北京/上海/成都等), 只能给线路与站表")
    if result.get("planTime"):
        print(f"  数据时间: {result['planTime']}")
    if result.get("firstTime"):
        print(f"  首班 {result['firstTime']}  末班 {result['lastTime']}")
    if result.get("price"):
        print(f"  票价: {result['price']}")
    if result.get("state"):
        print(f"  运营状态: {result['state']}")
    if result.get("tip"):
        print(f"  上游提示: {result['tip']}")
    if result["predictions"]:
        print("  到站预测:")
        for p in result["predictions"]:
            bits = []
            if p.get("minutesText"):
                bits.append(p["minutesText"])
            if p.get("stopsText"):
                bits.append(p["stopsText"])
            elif p.get("stopsAway"):
                bits.append(f"还有 {p['stopsAway']} 站")
            if p.get("distanceText"):
                bits.append(f"距 {p['distanceText']}")
            elif p.get("distanceMeters"):
                bits.append(f"距 {p['distanceMeters']}米")
            if p.get("arriveAt"):
                bits.append(f"约 {p['arriveAt']} 到")
            where = f" → {p['station']}" if p.get("station") else ""
            print(f"    车 {p.get('busNumber')}: " + (" / ".join(bits) if bits else "—") + where)
    if result["buses"]:
        print(f"  在途车辆 {len(result['buses'])} 辆:")
        for b in result["buses"][:12]:
            dist = b.get("distanceToNextStation")
            # 距离为 0 通常是上游没给(而不是真在站口), 显示成"—"比"0米"诚实
            dist_s = f"{dist:.0f}米" if isinstance(dist, (int, float)) and dist > 0 else "—"
            print(f"    {b.get('busNumber'):<12} 下一站 {b.get('nextStation') or '—'} ({dist_s})")
    else:
        print("  当前没有在途车辆")
    return 0


def cmd_station(args):
    city = normalize_city(args.city)
    src = pick_source(city, args.src)
    if not src:
        die(f"两个数据源都没覆盖「{city}」")
    if src == "mygolbs":
        stations = mg_station_search(city, args.station)
        # CMD=102 会把上下行各返回一遍 —— 同一个站会出现两次, 按 (站名, 线路集合) 去重
        seen = set()
        matches = []
        routes = []
        for st in stations:
            key = (st.get("stationName"), tuple(st.get("relatedRoutes") or []))
            if key in seen:
                continue
            seen.add(key)
            matches.append({"stationName": st.get("stationName"),
                            "sameNameNum": st.get("sameNameNum"),
                            "relatedRoutes": st.get("relatedRoutes")})
            for r in st.get("relatedRoutes") or []:
                if r not in routes:
                    routes.append(r)
        out = {"city": city, "source": src, "station": args.station,
               "matches": matches, "routes": routes}
    else:
        catalog = cl_lines(city)
        routes = []
        for name, recs in catalog.items():
            for rec in recs:
                st = cl_route(rec.get("lineId"), city)
                if any(args.station in (x.get("sn") or "") for x in st):
                    routes.append({"lineName": name, "lineId": rec.get("lineId"),
                                   "from": rec.get("startStopName"), "to": rec.get("endStopName"),
                                   "firstTime": rec.get("firstTime"), "lastTime": rec.get("lastTime")})
                    break
        out = {"city": city, "source": src, "station": args.station, "routes": routes}

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"{out['city']}  站点「{args.station}」  (数据源 {src})")
    if src == "mygolbs":
        for m in out["matches"]:
            print(f"  {m['stationName']}  (同名 {m.get('sameNameNum')} 个)")
            for r in (m.get("relatedRoutes") or []):
                print(f"    - {r}")
        if not out["matches"]:
            print("  没查到该站点")
    else:
        for r in out["routes"]:
            print(f"  - {r['lineName']}  {r['from']} → {r['to']}  "
                  f"首班 {r.get('firstTime')} 末班 {r.get('lastTime')}")
        if not out["routes"]:
            print("  没查到该站点")
    return 0


def cmd_route(args):
    """起点站 ∩ 终点站 = 可直达的线路。

    方向判定**按站序**, 不靠站名猜 —— 同一对站常常两个方向都能到, 区别在于
    哪个方向上起点站在终点站前面。
    """
    city = normalize_city(args.city)
    src = pick_source(city, args.src)
    if not src:
        die(f"两个数据源都没覆盖「{city}」")
    out = {"city": city, "source": src, "origin": args.origin,
           "destination": args.destination, "direct": []}

    if src == "mygolbs":
        catalog = mg_lines(city)
        routes_a, routes_b = set(), set()
        for st in mg_station_search(city, args.origin):
            routes_a.update(st.get("relatedRoutes") or [])
        for st in mg_station_search(city, args.destination):
            routes_b.update(st.get("relatedRoutes") or [])
        common = sorted(routes_a & routes_b)
        for name in common:
            for direction, rec in (catalog.get(name) or {}).items():
                stations = mg_stations(city, name, direction)
                o_st = match_station(stations, args.origin)
                d_st = match_station(stations, args.destination)
                if not o_st or not d_st:
                    continue
                o_no, d_no = order_of(o_st), order_of(d_st)
                if not o_no or not d_no:
                    continue
                item = {
                    "lineName": name, "direction": direction,
                    "from": rec.get("from"), "to": rec.get("to"),
                    "originOrder": o_no, "destOrder": d_no,
                    "stops": d_no - o_no,
                }
                if o_no < d_no:
                    item["usable"] = True
                else:
                    item["usable"] = False
                    item["hint"] = "这个方向坐反了, 往反方向坐"
                out["direct"].append(item)
    else:
        catalog = cl_lines(city)
        routes_a, routes_b = set(), set()
        for name, recs in catalog.items():
            for rec in recs:
                names = [x.get("sn") or "" for x in cl_route(rec.get("lineId"), city)]
                if any(args.origin in n for n in names):
                    routes_a.add(name)
                if any(args.destination in n for n in names):
                    routes_b.add(name)
        for name in sorted(routes_a & routes_b):
            for rec in catalog[name]:
                stations = cl_route(rec.get("lineId"), city)
                o_st = match_station(stations, args.origin)
                d_st = match_station(stations, args.destination)
                if not o_st or not d_st:
                    continue
                o_no, d_no = order_of(o_st), order_of(d_st)
                if not o_no or not d_no:
                    continue
                item = {
                    "lineName": name, "lineId": rec.get("lineId"),
                    "from": rec.get("startStopName"), "to": rec.get("endStopName"),
                    "firstTime": rec.get("firstTime"), "lastTime": rec.get("lastTime"),
                    "originOrder": o_no, "destOrder": d_no, "stops": d_no - o_no,
                    "usable": o_no < d_no,
                }
                if o_no >= d_no:
                    item["hint"] = "这个方向坐反了, 往反方向坐"
                out["direct"].append(item)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"{out['city']}  {out['origin']} → {out['destination']}  (数据源 {src})")
    usable = [d for d in out["direct"] if d.get("usable")]
    if not usable:
        if out["direct"]:
            print("  找到共线线路, 但方向都坐反了, 请看下面的方向说明:")
        else:
            print("  没有直达线路(本技能只做直达, 不做换乘规划)")
    for d in usable:
        print(f"  ✓ {d['lineName']} 方向{d.get('direction', '-')}  {d.get('from')} → {d.get('to')}")
        print(f"      起点第 {d['originOrder']} 站 → 终点第 {d['destOrder']} 站"
              f"(约 {d['stops']} 站)")
        if d.get("firstTime"):
            print(f"      首班 {d['firstTime']} 末班 {d.get('lastTime')}")
    for d in out["direct"]:
        if not d.get("usable"):
            print(f"  ✗ {d['lineName']} 方向{d.get('direction', '-')}  "
                  f"{d.get('from')} → {d.get('to')}  (起点第 {d['originOrder']} 站, "
                  f"终点第 {d['destOrder']} 站 —— {d.get('hint')})")
    return 0 if usable else 1


def cmd_scan(args):
    """全城扫: 哪些线路此刻有车。

    线路多的时候逐条查很慢 —— 用 --max-probe 限制探测条数, 探够了就停。
    """
    city = normalize_city(args.city)
    src = pick_source(city, args.src)
    if not src:
        die(f"两个数据源都没覆盖「{city}」")
    if src != "mygolbs":
        die("全城扫描只支持掌上公交(车来了要逐条查线路, 太慢)")
    catalog = mg_lines(city)
    hits = []
    probed = 0
    for name, dirs in sorted(catalog.items()):
        for direction in sorted(dirs):
            if probed >= args.max_probe:
                break
            probed += 1
            try:
                data = mg_live(city, name, direction)
            except SystemExit:
                continue
            buses = data.get("list") or []
            if buses:
                rec = dirs[direction]
                hits.append({
                    "lineName": name, "direction": direction,
                    "from": rec.get("from"), "to": rec.get("to"),
                    "busCount": len(buses),
                    "buses": [{"busNumber": b.get("busNumber"),
                               "nextStation": b.get("stationName"),
                               "distance": b.get("busToStationNiheDistance")} for b in buses],
                })
            if len(hits) >= args.limit:
                break
        if len(hits) >= args.limit or probed >= args.max_probe:
            break
    out = {"city": city, "source": src, "totalLines": len(catalog),
           "probed": probed, "active": hits}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"{city}  线路总数 {len(catalog)}  探测 {probed} 条  "
          f"此刻有车 {len(hits)} 条  (数据源 {src})")
    if probed >= args.max_probe and len(hits) < args.limit:
        print(f"  (探测上限 {args.max_probe} 条已到, 还有线路没扫)")
    for h in hits:
        print(f"  - {h['lineName']} 方向{h['direction']}  {h['from']} → {h['to']}  "
              f"({h['busCount']} 辆)")
        for b in h["buses"][:4]:
            d = b.get("distance")
            print(f"      {b.get('busNumber')} 下一站 {b.get('nextStation')} "
                  f"({f'{d:.0f}米' if isinstance(d, (int, float)) and d > 0 else '—'})")
    return 0


def cmd_cities(args):
    mg = sorted(mygolbs_cities())
    cl = sorted(chelaile_cities().keys())
    if args.src == "chelaile":
        print(f"车来了覆盖 {len(cl)} 城:")
        for c in cl:
            print(f"  {c}")
        return 0
    print(f"掌上公交覆盖 {len(mg)} 城/县:")
    for c in mg:
        print(f"  {c}")
    if not args.src:
        print(f"\n车来了覆盖 {len(cl)} 城(含港澳台与境外), 车来了城市ID见 references/cities.json")
    return 0


# ---------------------------------------------------------------- 入口

def build_parser():
    p = argparse.ArgumentParser(
        prog="bus_query.py",
        description="公交实时查询(掌上公交 + 车来了)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--src", choices=["mygolbs", "chelaile"], default=None,
                        help="强制数据源(默认掌上公交优先, 没有再退车来了)")
        sp.add_argument("--json", action="store_true", help="输出原始 JSON")
        sp.add_argument("--limit", type=int, default=40, help="最多显示几条(默认 40)")

    sp = sub.add_parser("lines", help="列线路目录")
    sp.add_argument("city", nargs="?", default=None, help="城市名(不写就用默认城市)")
    common(sp)
    sp.set_defaults(func=cmd_lines)

    sp = sub.add_parser("live", help="查线路实时车辆")
    sp.add_argument("city", nargs="?", default=None, help="城市名(不写就用默认城市)")
    sp.add_argument("line")
    sp.add_argument("--dir", dest="direction", choices=["1", "2"], default=None,
                    help="方向: 1 上行 / 2 下行(默认按目标站自动判断)")
    sp.add_argument("--to", default=None, help="目标站名(给了就附带到站预测: 还有几站/几分钟)")
    common(sp)
    sp.set_defaults(func=cmd_live)

    sp = sub.add_parser("station", help="查站点经过哪些线路")
    sp.add_argument("city", nargs="?", default=None, help="城市名(不写就用默认城市)")
    sp.add_argument("station")
    common(sp)
    sp.set_defaults(func=cmd_station)

    sp = sub.add_parser("route", help="查起点到终点的直达线路")
    sp.add_argument("city", nargs="?", default=None, help="城市名(不写就用默认城市)")
    sp.add_argument("origin")
    sp.add_argument("destination")
    common(sp)
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser("scan", help="全城扫: 哪些线路此刻有车")
    sp.add_argument("city", nargs="?", default=None, help="城市名(不写就用默认城市)")
    sp.add_argument("--max-probe", type=int, default=80,
                    help="最多探测多少条线路方向(默认 80, 防止太慢)")
    common(sp)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("cities", help="列出数据源覆盖的城市")
    common(sp)
    sp.set_defaults(func=cmd_cities)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n[bus] 已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
