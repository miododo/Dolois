# Dolois

## 茶竹论坛二手房爬虫（XPath）

爬取地址：`https://fc.cqyc.net/resoldhome/esf/list`

抓取字段：
- 标题（title）
- 户型（house_type）
- 面积（area）
- 楼层（floor）
- 小区名称（community）
- 地址（address）
- 总价（total_price）
- 房屋编号（house_no）
- 发布时间（publish_time）
- 看房人数（view_count）
- 图片链接（image_url）

## 使用方式

```bash
pip install -r requirements.txt
python spider/esf_spider.py --pages 2 --format json --out output/esf_houses.json
```

输出也支持 CSV：

```bash
python spider/esf_spider.py --pages 2 --format csv --out output/esf_houses.csv
```

> 说明：网页结构可能变化，`spider/esf_spider.py` 里已提供多组 XPath 兜底；若某字段为空，请按页面实际结构微调 XPath。
