import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from scripts import collect_marketplaces as collector


def joongna_page(*items):
    return {"data": {"totalSize": len(items), "items": list(items)}}


def joongna_raw(seq, state, sort_date, price=500_000):
    return {"seq": seq, "title": f"리코 gr3 {seq}", "price": price, "state": state, "sortDate": sort_date, "storeSeq": 77}


class JoongnaCollectorTest(unittest.TestCase):
    def test_splits_on_sale_and_sold_and_stops_at_cutoff(self):
        pages = [
            joongna_page(
                joongna_raw(1, 0, "2026-10-09 10:00:00"),
                joongna_raw(2, 3, "2026-10-08 10:00:00"),
                joongna_raw(3, 1, "2026-10-08 09:00:00"),
                joongna_raw(4, 0, "2026-08-01 09:00:00"),
            ),
            joongna_page(joongna_raw(5, 0, "2026-10-01 10:00:00")),
        ]
        cutoff = datetime(2026, 9, 14, tzinfo=timezone.utc)
        with mock.patch.object(collector, "request_json", side_effect=pages) as request, \
                mock.patch.object(collector.time, "sleep"):
            result = collector.collect_joongna("리코 gr3", cutoff, max_pages=5)
        self.assertEqual(request.call_count, 1)
        self.assertEqual([item["sequence"] for item in result["available_listings"]], [1])
        sold = result["sold_price_history"]["listings"]
        self.assertEqual([item["sequence"] for item in sold], [2])
        self.assertEqual(sold[0]["sorted_at"], "2026-10-08T10:00:00+09:00")
        self.assertEqual(sold[0]["seller_id"], 77)
        self.assertEqual(sold[0]["listing_url"], "https://web.joongna.com/product/2")


class BunjangCollectorTest(unittest.TestCase):
    def test_skips_ads_and_follows_cursor(self):
        def page(items, cursor):
            return {"data": {"responses": {"mainGrid": {"searchResponse": {
                "data": items, "cursor": cursor, "totalCount": 3,
            }}}}}

        product = {"type": "PRODUCT", "ad": False, "status": "SELLING", "price": 400_000, "shop": {"uid": 9}}
        pages = [
            page([
                {**product, "pid": 10, "name": "리코 gr3", "updatedAt": "2026-10-09T01:00:00Z"},
                {"type": "EXT_AD", "pid": None},
                {**product, "pid": 11, "name": "광고", "ad": True, "updatedAt": "2026-10-09T01:00:00Z"},
            ], "next"),
            page([{**product, "pid": 12, "name": "리코 gr3", "updatedAt": "2026-10-08T01:00:00Z"}], None),
        ]
        cutoff = datetime(2026, 9, 14, tzinfo=timezone.utc)
        with mock.patch.object(collector, "request_json", side_effect=pages) as request, \
                mock.patch.object(collector.time, "sleep"):
            result = collector.collect_bunjang("리코 gr3", cutoff, max_pages=5)
        self.assertIn("cursor=next", request.call_args_list[1].args[0])
        self.assertEqual([item["product_id"] for item in result["listings"]], [10, 12])
        self.assertEqual(result["listings"][0]["seller_id"], 9)
        self.assertEqual(result["listings"][0]["listing_url"], "https://m.bunjang.co.kr/products/10")


class SearchQueryConfigTest(unittest.TestCase):
    def test_every_catalog_model_has_one_search_word(self):
        import json

        queries = json.loads(collector.QUERIES.read_text())["queries"]
        catalog = json.loads((collector.ROOT / "data" / "catalog" / "products.json").read_text())["products"]
        models = [query["model"] for query in queries]
        self.assertEqual(len(models), len(set(models)))
        self.assertEqual(set(models), {product["model"] for product in catalog})
        self.assertTrue(all(query["search_word"].strip() for query in queries))


if __name__ == "__main__":
    unittest.main()


class JoongnaDescriptionTest(unittest.TestCase):
    def test_reads_referenced_text_chunk(self):
        from scripts.collect_marketplaces import joongna_description_from_html
        body = "용량 256GB\n잔상 없음 😀"
        size = format(len(body.encode()), "x")
        chunks = [
            [1, f'6:["$","x",null,{{"productTitle":"아이폰","productDescription":"$41"}}]\n'],
            [1, f"41:T{size},{body}"],
        ]
        html = "".join(f"<script>self.__next_f.push({json.dumps(chunk, ensure_ascii=False)})</script>" for chunk in chunks)
        self.assertEqual(joongna_description_from_html(html), body)

    def test_inline_description(self):
        from scripts.collect_marketplaces import joongna_description_from_html
        chunk = [1, '6:{"productDescription":"바로 적힌 본문"}']
        html = f"<script>self.__next_f.push({json.dumps(chunk, ensure_ascii=False)})</script>"
        self.assertEqual(joongna_description_from_html(html), "바로 적힌 본문")
