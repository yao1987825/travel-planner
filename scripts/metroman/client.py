"""HTTP 客户端 —— 纯标准库（urllib），带磁盘缓存。

站点为 ASP.NET MVC 服务端渲染，没有公开 REST 接口，但线网页面内嵌 JSON
地图数据，且 `/network/{city}/routes` 暴露了一个 JSON 路线接口。
详见 references/metro_api.md。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

BASE_URL = "https://www.metroman.cn"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class MetroManError(Exception):
    """通用错误。"""


class NotFoundError(MetroManError):
    """资源不存在（城市、车站、线路或路线）。"""


class HttpError(MetroManError):
    """HTTP 请求失败。"""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def default_cache_dir() -> Path:
    base = os.environ.get("METROMAN_CACHE_DIR")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CACHE_HOME")
    root = Path(xdg) if xdg else Path.home() / ".cache"
    return root / "metroman"


class MetroManClient:
    """带缓存的站点抓取客户端。"""

    def __init__(
        self,
        base_url: str = BASE_URL,
        cache_dir: Optional[Path] = None,
        timeout: float = 25.0,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------ URL

    def url_for(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    # --------------------------------------------------------------- cache

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        folder = self.cache_dir / digest[:2]
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return folder / f"{digest}.json"

    def _read_cache(self, url: str, ttl: float) -> Optional[str]:
        if ttl <= 0:
            return None
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if time.time() - payload.get("ts", 0) > ttl:
            return None
        return payload.get("body")

    def _write_cache(self, url: str, body: str, status: int) -> None:
        path = self._cache_path(url)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"url": url, "ts": time.time(), "status": status, "body": body},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError:
            pass

    # ---------------------------------------------------------------- fetch

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        ttl: float = 300.0,
        use_cache: bool = True,
    ) -> str:
        """发起 GET 请求并返回响应正文（HTML 或 JSON 文本）。"""
        url = self.url_for(path)
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        if use_cache and ttl > 0:
            cached = self._read_cache(url, ttl)
            if cached is not None:
                return cached

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
                encoding = (response.headers.get("Content-Encoding") or "").lower()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(f"未找到资源：{url}") from exc
            raise HttpError(f"HTTP {exc.code}：{url}", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise HttpError(f"请求失败：{url}（{exc.reason}）") from exc
        except OSError as exc:
            raise HttpError(f"请求失败：{url}（{exc}）") from exc

        if encoding == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        elif encoding == "deflate":
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error:
                pass

        body = raw.decode("utf-8", errors="replace")

        if use_cache and ttl > 0:
            self._write_cache(url, body, status)
        return body

    def get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        ttl: float = 300.0,
        use_cache: bool = True,
    ) -> Any:
        body = self.get(path, params=params, ttl=ttl, use_cache=use_cache)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise HttpError(f"响应不是合法 JSON：{path}") from exc
