"""极简 HTML DOM —— 只用标准库实现的最小解析器。

为什么不用 lxml/BeautifulSoup：
    这个技能要能在 RikkaHub 的 proot 工作区里跑, 那边的 python 是裸装的,
    装 lxml 要编译。所以这里用标准库 `html.parser` 搭一个够用的小 DOM。

支持的操作(覆盖 metroman 解析所需的全部能力)：

    node.find_all(tag="a", cls="city-line-code")   # 找后代
    node.find(tag="h3")                              # 找第一个后代
    node.text_content()                              # 纯文本
    node.get("href")                                 # 取属性
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Dict, List, Optional

# 不需要闭合标签的 void 元素
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

# 这些标签的内容不是文本
SKIP_TEXT_TAGS = {"script", "style", "noscript", "template"}


class Node:
    """DOM 节点。"""

    __slots__ = ("tag", "attrs", "children", "parent", "_text")

    def __init__(self, tag: str, attrs: Optional[Dict[str, str]] = None,
                 parent: Optional["Node"] = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: List["Node"] = []
        self.parent = parent
        self._text: List[str] = []

    # ---------------------------------------------------------------- 属性

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    @property
    def classes(self) -> List[str]:
        return (self.get("class") or "").split()

    # ---------------------------------------------------------------- 文本

    def text_content(self) -> str:
        parts: List[str] = list(self._text)
        for child in self.children:
            parts.append(child.text_content())
        return "".join(parts)

    # ---------------------------------------------------------------- 查找

    def iter_descendants(self):
        for child in self.children:
            yield child
            yield from child.iter_descendants()

    def find_all(self, tag: Optional[str] = None,
                 cls: Optional[str] = None,
                 attr: Optional[str] = None,
                 attr_value: Optional[str] = None) -> List["Node"]:
        """按标签名 / class 片段 / 属性查找全部后代节点。"""
        result = []
        for node in self.iter_descendants():
            if tag and node.tag != tag:
                continue
            if cls and not any(cls in c for c in node.classes):
                continue
            if attr is not None:
                if attr not in node.attrs:
                    continue
                if attr_value is not None and node.attrs.get(attr) != attr_value:
                    continue
            result.append(node)
        return result

    def find(self, tag: Optional[str] = None,
             cls: Optional[str] = None,
             attr: Optional[str] = None,
             attr_value: Optional[str] = None) -> Optional["Node"]:
        for node in self.iter_descendants():
            if tag and node.tag != tag:
                continue
            if cls and not any(cls in c for c in node.classes):
                continue
            if attr is not None:
                if attr not in node.attrs:
                    continue
                if attr_value is not None and node.attrs.get(attr) != attr_value:
                    continue
            return node
        return None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.tag} {self.attrs}>"


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self._stack: List[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs) -> None:
        node = Node(tag, {k: (v or "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        node = Node(tag, {k: (v or "") for k, v in attrs}, self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        current = self._stack[-1]
        if current.tag in SKIP_TEXT_TAGS:
            return
        current._text.append(data)


def parse_html(html: str) -> Node:
    """把 HTML 字符串解析成 Node 树（返回 #document 根节点）。"""
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def clean_text(value: str) -> str:
    """把文本压成单行并去掉多余空白。"""
    return " ".join(unescape(value or "").split())
