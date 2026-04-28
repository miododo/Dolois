#!/usr/bin/env python3
"""茶竹论坛二手房信息爬虫（基于用户给定结构补充字段与翻页）。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from lxml import etree

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


# 发送请求，获取页面内容
def getHtml(url: str, timeout: int = 20):
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
    htmlstr = response.text
    htmltree = etree.HTML(htmlstr)
    return htmltree


# 安全提取单个文本
def getOne(xpath_result, default: str = "") -> str:
    if len(xpath_result) > 0:
        return str(xpath_result[0]).strip()
    return default


def join_clean_text(values) -> str:
    return " ".join(str(x).strip() for x in values if str(x).strip())


def regex_pick(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0).strip()
    return ""


# 解析二手房列表页（只获取二手房的链接）
def getHousehref(htmltree: etree._Element) -> list[str]:
    path = '//div[@class="main-left"]/ul/li/div[1]/a[1]/@href'
    rel_links = htmltree.xpath(path)
    if not rel_links:
        # 页面结构兜底
        rel_links = htmltree.xpath("//a[contains(@href,'/resoldhome/esf/detail')]/@href")

    abs_links: list[str] = []
    seen = set()
    for link in rel_links:
        link = str(link).strip()
        if not link:
            continue
        full = link if link.startswith("http") else f"{BASE_URL}{link}"
        if full not in seen:
            seen.add(full)
            abs_links.append(full)
    return abs_links


# 从详情页补足列表页未抓到的字段
# 解析二手房详情页，获取房屋信息
def getHouseInfo(htmltree: etree._Element, detail_url: str = "") -> dict:
    house: dict[str, str] = {}
    all_text = join_clean_text(htmltree.xpath("//text()"))

    # 获取标题
    house["title"] = getOne(htmltree.xpath('/html/body/div[4]/div/div[3]/p/text()')) or getOne(
        htmltree.xpath("//div[contains(@class,'title')]//p/text()")
    )

    # 房屋编号
    raw_no = getOne(htmltree.xpath("//div[@class='detail-top clearfix']/div[1]/span[1]/text()"))
    if not raw_no:
        raw_no = regex_pick(all_text, [r"(?:房屋编号|房源编号|编号)\s*[:：]?\s*[A-Za-z0-9_-]+"])
    no_num = re.findall(r"([A-Za-z0-9_-]+)", raw_no)
    house["house_no"] = no_num[-1] if no_num else ""

    # 房屋图片链接
    imgs = htmltree.xpath('//div[@class="detailImg"]//img/@src')
    if not imgs:
        imgs = htmltree.xpath("//img[contains(@class,'house') or contains(@class,'pic')]/@src")
    cleaned: list[str] = []
    for img in imgs:
        img = str(img).split("?")[0].strip()
        if not img:
            continue
        if not img.startswith("http"):
            img = f"{BASE_URL}{img}" if img.startswith("/") else f"{BASE_URL}/{img}"
        if img not in cleaned:
            cleaned.append(img)
    house["image_urls"] = ",".join(cleaned)

    # 发布时间
    dt = htmltree.xpath('/html/body/div[4]/div/div[3]/div[1]/span[2]/text()')
    dt = dt[0].split(":")[-1].strip() if len(dt) > 0 else ""
    if not dt:
        dt = regex_pick(all_text, [r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?"])
    house["publish_time"] = dt

    # 以下为补充字段
    house["house_type"] = regex_pick(all_text, [r"\d+\s*室\s*\d*\s*厅\s*\d*\s*卫?"])
    house["area"] = regex_pick(all_text, [r"\d+(?:\.\d+)?\s*(?:㎡|m²|平米|平方米)"])
    house["floor"] = regex_pick(
        all_text,
        [r"(?:低层|中层|高层|底层|顶层|地下)\s*(?:/\s*\d+层)?", r"\d+\s*/\s*\d+\s*层", r"共\s*\d+\s*层"],
    )
    house["community_name"] = getOne(htmltree.xpath("//a[contains(@href,'xiaoqu')]/text()"))
    if not house["community_name"]:
        house["community_name"] = regex_pick(all_text, [r"小区[:：]?\s*[^\s，,。]{2,}"])
        house["community_name"] = re.sub(r"^小区[:：]?\s*", "", house["community_name"])

    house["address"] = getOne(htmltree.xpath("//*[contains(text(),'地址')]/following-sibling::*[1]//text()"))
    if not house["address"]:
        house["address"] = regex_pick(all_text, [r"(?:地址|位置|所在地址)[:：]?\s*[^\n，。]{4,}"])
        house["address"] = re.sub(r"^(?:地址|位置|所在地址)[:：]?\s*", "", house["address"])

    house["total_price"] = regex_pick(all_text, [r"\d+(?:\.\d+)?\s*(?:万|万元)"])
    house["view_count"] = regex_pick(all_text, [r"\d+\s*人看房", r"\d+\s*次浏览", r"浏览\s*\d+"])

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
            htmltree = getHtml(url)
        except requests.RequestException as exc:
            print(f"列表页请求失败: {url} ({exc})")
            continue

        househreflist = getHousehref(htmltree)
        if not househreflist:
            print("当前页未找到详情链接，可能到达末页或页面结构变化。")
            continue

        for link in househreflist:
            if link in seen:
                continue
            seen.add(link)
            try:
                housetree = getHtml(link)
                house = getHouseInfo(housetree, detail_url=link)
                houses.append(parse_house_info(house))
            except requests.RequestException as exc:
                print(f"详情页请求失败: {link} ({exc})")
                continue
            time.sleep(delay)

        time.sleep(delay)

    return houses


def save_csv(items: list[HouseItem], filename: Path) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
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
    with filename.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(field_map.values()))
        writer.writeheader()
        for item in items:
            row = asdict(item)
            writer.writerow({cn: row[key] for key, cn in field_map.items()})


def save_json(items: list[HouseItem], filename: Path) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    with filename.open("w", encoding="utf-8") as f:
        json.dump([asdict(x) for x in items], f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="采集茶竹房产二手房信息")
    parser.add_argument("--start-page", type=int, default=1, help="起始页，默认 1")
    parser.add_argument("--end-page", type=int, default=1, help="结束页，默认 1")
    parser.add_argument("--delay", type=float, default=0.8, help="请求间隔秒数，默认 0.8")
    parser.add_argument("--output", type=Path, default=Path("output/cqyc_second_hand_houses.csv"), help="CSV 输出文件")
    parser.add_argument("--json-output", type=Path, default=None, help="可选 JSON 输出文件")
    args = parser.parse_args()

    if args.start_page <= 0 or args.end_page <= 0 or args.start_page > args.end_page:
        raise ValueError("页码参数非法：需满足 start-page >= 1 且 end-page >= start-page")

    houses = crawl_houses(start_page=args.start_page, end_page=args.end_page, delay=args.delay)
    save_csv(houses, args.output)
    if args.json_output:
        save_json(houses, args.json_output)

    print(f"采集完成，共 {len(houses)} 条，CSV 已保存到: {args.output}")
    if args.json_output:
        print(f"JSON 已保存到: {args.json_output}")


if __name__ == "__main__":
    main()
