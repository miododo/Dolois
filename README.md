# Dolois

## 茶竹论坛二手房爬虫（XPath）

爬取地址：`https://fc.cqyc.net/resoldhome/esf/list`

抓取字段：
- 标题（title）
- 户型（house_type）
- 面积（area）
- 楼层（floor）
- 小区名称（community_name）
- 地址（address）
- 总价（total_price）
- 房屋编号（house_no）
- 发布时间（publish_time）
- 看房人数（view_count）
- 房屋图片链接（image_urls）
- 详情链接（detail_url）

## 使用方式

```bash
pip install -r requirements.txt
python spider/esf_spider.py --start-page 1 --end-page 2 --output output/esf_houses.csv
```

同时导出 JSON：

```bash
python spider/esf_spider.py --start-page 1 --end-page 2 --output output/esf_houses.csv --json-output output/esf_houses.json
```

> 说明：脚本保留了你给定的函数结构（`getHtml/getHousehref/getHouseInfo`），在此基础上补齐字段抓取并增加翻页区间采集。
