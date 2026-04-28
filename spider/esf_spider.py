#!/usr/bin/env python3
"""茶竹论坛二手房信息爬虫（XPath 解析版）。

目标站点: https://fc.cqyc.net/resoldhome/esf/list
抓取字段:
- 标题
- 户型
- 面积
- 楼层
- 小区名称
- 地址
- 总价
- 房屋编号
- 发布时间
- 看房人数
- 房源图片链接
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List

import requests
from lxml import etree
from requests import Response

BASE_URL = "https://fc.cqyc.net"
LIST_URL = f"{BASE_URL}/resoldhome/esf/list"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


@dataclass
class HouseItem:
    title: str
    house_type: str
    area: str
    floor: str
    community: str
    address: str
    total_price: str
    house_no: str
    publish_time: str
    view_count: str
    image_url: str


class EsfSpider:
    """基于 requests + lxml 的二手房爬虫。"""

    def __init__(self, delay: float = 0.5, timeout: int = 20) -> None:
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self, url: str) -> Response:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp

    def parse_list_page(self, html: str) -> List[HouseItem]:
        root = etree.HTML(html)

        # 以下 XPath 为该类型房源列表页常见结构写法：
        # 若页面结构有细微变化，可改这两行 XPath。
        card_nodes = root.xpath("//ul[contains(@class,'house-list')]//li")
        if not card_nodes:
            card_nodes = root.xpath("//div[contains(@class,'house-item')]")

        items: List[HouseItem] = []
        for node in card_nodes:
            item = HouseItem(
                title=self._first_text(
                    node,
                    [
                        ".//h3//a/text()",
                        ".//p[contains(@class,'title')]//a/text()",
                        ".//a[contains(@class,'title')]/text()",
                    ],
                ),
                house_type=self._first_text(
                    node,
                    [
                        ".//p[contains(@class,'info')]//span[1]/text()",
                        ".//div[contains(@class,'meta')]/span[1]/text()",
                    ],
                ),
                area=self._extract_by_regex(
                    node,
                    [
                        ".//p[contains(@class,'info')]//span[2]/text()",
                        ".//div[contains(@class,'meta')]/span[2]/text()",
                    ],
                    r"\d+(?:\.\d+)?\s*㎡",
                ),
                floor=self._first_text(
                    node,
                    [
                        ".//p[contains(@class,'info')]//span[3]/text()",
                        ".//div[contains(@class,'meta')]/span[3]/text()",
                    ],
                ),
                community=self._first_text(
                    node,
                    [
                        ".//p[contains(@class,'community')]//a/text()",
                        ".//a[contains(@href,'community')]/text()",
                    ],
                ),
                address=self._first_text(
                    node,
                    [
                        ".//p[contains(@class,'address')]/text()",
                        ".//span[contains(@class,'address')]/text()",
                    ],
                ),
                total_price=self._extract_by_regex(
                    node,
                    [
                        ".//div[contains(@class,'price')]//text()",
                        ".//p[contains(@class,'price')]//text()",
                    ],
                    r"\d+(?:\.\d+)?\s*万",
                ),
                house_no=self._extract_label_value(node, ["房屋编号", "编号", "房源编号"]),
                publish_time=self._extract_label_value(node, ["发布时间", "发布"]),
                view_count=self._extract_label_value(node, ["看房人数", "看房", "浏览"]),
                image_url=self._first_attr(
                    node,
                    [
                        ".//img/@data-src",
                        ".//img/@src",
                    ],
                ),
            )

            item.image_url = self._to_abs_url(item.image_url)
            if any(asdict(item).values()):
                items.append(item)

        return items

    def crawl(self, pages: int = 1) -> List[HouseItem]:
        all_items: List[HouseItem] = []

        for page in range(1, pages + 1):
            page_url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
            print(f"[+] 抓取第 {page} 页: {page_url}")
            resp = self.fetch(page_url)
            page_items = self.parse_list_page(resp.text)
            print(f"    解析到 {len(page_items)} 条房源")
            all_items.extend(page_items)
            time.sleep(self.delay)

        return all_items

    @staticmethod
    def _first_text(node: etree._Element, xpaths: Iterable[str]) -> str:
        for xp in xpaths:
            values = [x.strip() for x in node.xpath(xp) if isinstance(x, str) and x.strip()]
            if values:
                return " ".join(values)
        return ""

    @staticmethod
    def _first_attr(node: etree._Element, xpaths: Iterable[str]) -> str:
        for xp in xpaths:
            values = [x.strip() for x in node.xpath(xp) if isinstance(x, str) and x.strip()]
            if values:
                return values[0]
        return ""

    def _extract_by_regex(self, node: etree._Element, xpaths: Iterable[str], pattern: str) -> str:
        text = self._first_text(node, xpaths)
        if not text:
            return ""
        m = re.search(pattern, text)
        return m.group(0) if m else text

    @staticmethod
    def _extract_label_value(node: etree._Element, labels: List[str]) -> str:
        joined_text = " ".join(
            x.strip() for x in node.xpath(".//text()") if isinstance(x, str) and x.strip()
        )
        for label in labels:
            m = re.search(rf"{re.escape(label)}[：:]?\s*([^\s，,|]+)", joined_text)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _to_abs_url(url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"{BASE_URL}{url}"
        return f"{BASE_URL}/{url}"


def save_json(items: List[HouseItem], out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps([asdict(x) for x in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_csv(items: List[HouseItem], out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(HouseItem.__annotations__.keys())
    with out_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def main() -> None:
    parser = argparse.ArgumentParser(description="茶竹论坛二手房 XPath 爬虫")
    parser.add_argument("--pages", type=int, default=1, help="抓取页数，默认 1")
    parser.add_argument(
        "--out", type=Path, default=Path("output/esf_houses.json"), help="输出文件路径"
    )
    parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="输出格式"
    )
    parser.add_argument("--delay", type=float, default=0.5, help="请求间隔秒数")
    args = parser.parse_args()

    spider = EsfSpider(delay=args.delay)
    items = spider.crawl(pages=args.pages)

    if args.format == "json":
        save_json(items, args.out)
    else:
        save_csv(items, args.out)

    print(f"\n[✓] 抓取完成，共 {len(items)} 条，保存到: {args.out}")


if __name__ == "__main__":
    main()
