#!/usr/bin/env python3
"""茶竹论坛二手房信息爬虫（仅使用 requests）。"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import asdict, dataclass

import requests

BASE_URL = "https://fc.cqyc.net"
LIST_URL = f"{BASE_URL}/resoldhome/esf/list"


@dataclass
class HouseItem:
    title: str = ""
    house_type: str = ""
    area: str = ""
    floor: str = ""
    community_name: str = ""
    address: str = ""
    total_price: str = ""
    house_no: str = ""
    publish_time: str = ""
    view_count: str = ""
    image_urls: str = ""
    detail_url: str = ""


# 发送请求，获取页面 HTML 文本
def getHtml(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return response.text


# 安全提取单个文本
def getOne(values, default: str = "") -> str:
    if values and len(values) > 0:
        return str(values[0]).strip()
    return default


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def regex_pick(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return ""


def to_abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url}"


# 解析二手房列表页（只获取二手房的链接）
def getHousehref(html: str) -> list[str]:
    patterns = [
        r'<div class="main-left"[\s\S]*?<ul[\s\S]*?(?:href=["\']([^"\']*/resoldhome/esf/detail[^"\']*)["\'])',
        r'href=["\']([^"\']*/resoldhome/esf/detail[^"\']*)["\']',
    ]

    links: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for link in re.findall(pattern, html, flags=re.I):
            full = to_abs_url(link)
            if full not in seen:
                seen.add(full)
                links.append(full)
        if links:
            break
    return links


# 解析二手房详情页，获取房屋信息
def getHouseInfo(html: str, detail_url: str = "") -> dict[str, str]:
    house: dict[str, str] = {}
    text = clean_text(html)

    house["title"] = regex_pick(
        html,
        [
            r"<p[^>]*>([^<]{4,})</p>",
            r"<h1[^>]*>([^<]+)</h1>",
            r"<h2[^>]*>([^<]+)</h2>",
        ],
    )

    house["house_no"] = regex_pick(
        text,
        [
            r"(?:房屋编号|房源编号|编号)\s*[:：]?\s*([A-Za-z0-9_-]+)",
        ],
    )

    # 图片链接
    img_candidates = re.findall(r"<img[^>]+(?:data-src|src)=[\"\']([^\"\']+)[\"\']", html, flags=re.I)
    imgs: list[str] = []
    for img in img_candidates:
        img = img.split("?")[0].strip()
        if not img:
            continue
        full = to_abs_url(img)
        if full not in imgs:
            imgs.append(full)
    house["image_urls"] = ",".join(imgs)

    house["publish_time"] = regex_pick(
        text,
        [
            r"(?:发布时间|发布日期|发布)\s*[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
            r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)",
        ],
    )

    house["house_type"] = regex_pick(text, [r"(\d+\s*室\s*\d*\s*厅\s*\d*\s*卫?)"])
    house["area"] = regex_pick(text, [r"(\d+(?:\.\d+)?\s*(?:㎡|m²|平米|平方米))"])
    house["floor"] = regex_pick(
        text,
        [r"((?:低层|中层|高层|底层|顶层|地下)\s*(?:/\s*\d+层)?)", r"(\d+\s*/\s*\d+\s*层)", r"(共\s*\d+\s*层)"],
    )
    house["community_name"] = regex_pick(text, [r"(?:小区名称|小区)\s*[:：]?\s*([^\s，,。]{2,})"])
    house["address"] = regex_pick(text, [r"(?:地址|位置|所在地址)\s*[:：]?\s*([^\n，。]{4,})"])
    house["total_price"] = regex_pick(text, [r"(\d+(?:\.\d+)?\s*(?:万|万元))"])
    house["view_count"] = regex_pick(text, [r"(\d+\s*人看房)", r"(\d+\s*次浏览)", r"(浏览\s*\d+)"])
    house["detail_url"] = detail_url

    return house


def parse_house_info(raw: dict[str, str]) -> HouseItem:
    return HouseItem(
        title=raw.get("title", ""),
        house_type=raw.get("house_type", ""),
        area=raw.get("area", ""),
        floor=raw.get("floor", ""),
        community_name=raw.get("community_name", ""),
        address=raw.get("address", ""),
        total_price=raw.get("total_price", ""),
        house_no=raw.get("house_no", ""),
        publish_time=raw.get("publish_time", ""),
        view_count=raw.get("view_count", ""),
        image_urls=raw.get("image_urls", ""),
        detail_url=raw.get("detail_url", ""),
    )


def get_page_url(page: int) -> str:
    return LIST_URL if page <= 1 else f"{LIST_URL}?page={page}"


def crawl_houses(start_page: int, end_page: int, delay: float) -> list[HouseItem]:
    houses: list[HouseItem] = []
    seen = set()

    for page in range(start_page, end_page + 1):
        url = get_page_url(page)
        print(f"正在采集第 {page} 页: {url}")
        try:
            list_html = getHtml(url)
        except requests.RequestException as exc:
            print(f"列表页请求失败: {url} ({exc})")
            continue

        links = getHousehref(list_html)
        if not links:
            print("当前页未找到详情链接，可能到达末页或页面结构变化。")
            continue

        for link in links:
            if link in seen:
                continue
            seen.add(link)
            try:
                detail_html = getHtml(link)
                house = getHouseInfo(detail_html, detail_url=link)
                houses.append(parse_house_info(house))
            except requests.RequestException as exc:
                print(f"详情页请求失败: {link} ({exc})")
                continue
            time.sleep(delay)

        time.sleep(delay)

    return houses


def save_csv(items: list[HouseItem], filename: str) -> None:
    field_map = {
        "title": "标题",
        "house_type": "户型",
        "area": "面积",
        "floor": "楼层",
        "community_name": "小区名称",
        "address": "地址",
        "total_price": "总价",
        "house_no": "房屋编号",
        "publish_time": "发布时间",
        "view_count": "看房人数",
        "image_urls": "房屋图片链接",
        "detail_url": "详情链接",
    }
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(field_map.values()))
        writer.writeheader()
        for item in items:
            row = asdict(item)
            writer.writerow({cn: row[key] for key, cn in field_map.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description="采集茶竹房产二手房信息")
    parser.add_argument("--start-page", type=int, default=1, help="起始页，默认 1")
    parser.add_argument("--end-page", type=int, default=1, help="结束页，默认 1")
    parser.add_argument("--delay", type=float, default=0.8, help="请求间隔秒数，默认 0.8")
    parser.add_argument("--output", default="cqyc_second_hand_houses.csv", help="CSV 输出文件名（导出到当前工作区）")
    args = parser.parse_args()

    if args.start_page <= 0 or args.end_page <= 0 or args.start_page > args.end_page:
        raise ValueError("页码参数非法：需满足 start-page >= 1 且 end-page >= start-page")

    houses = crawl_houses(start_page=args.start_page, end_page=args.end_page, delay=args.delay)
    save_csv(houses, args.output)
    print(f"采集完成，共 {len(houses)} 条，CSV 已保存到当前工作区: {args.output}")


if __name__ == "__main__":
    main()
