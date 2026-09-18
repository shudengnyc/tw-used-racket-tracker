"""Scraper and judging tests against saved Tennis Warehouse pages.

The fixtures are real pages captured on 2026-09-18. When Tennis Warehouse
changes its layout the live scrape breaks first; re-capture the pages, fix the
regexes until these pass, and update the expected values below.

    python3 -m unittest -v
"""
import gzip
import os
import unittest

import tw_used

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with gzip.open(os.path.join(FIX, name), "rt", encoding="utf-8") as f:
        return f.read()


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = tw_used.parse_catalog(fixture("catalog.html.gz"))

    def test_count_and_unique(self):
        self.assertEqual(len(self.cat), 74)
        self.assertEqual(len({c["code"] for c in self.cat}), 74)

    def test_first_racquet(self):
        self.assertEqual(self.cat[0], {
            "code": "WB9816", "name": "Wilson Blade 98 16x19 v9 Racquet",
            "brand": "Wilson", "new_price": 199.0, "list_price": 269.0,
            "rating": 4.7, "reviews": 39, "flags": ["sale"]})

    def test_every_racquet_has_the_basics(self):
        for c in self.cat:
            self.assertTrue(c["name"] and c["brand"], c)
            self.assertIsInstance(c["new_price"], float, c)


class ListingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        item = {"code": "WRFPR", "name": "Wilson RF 01 Pro Racquet",
                "brand": "Wilson", "new_price": 299.0, "list_price": 349.0,
                "rating": 4.5, "reviews": 40}
        cls.rows = tw_used.parse_listings(fixture("product.html.gz"), item, "u")

    def test_rows(self):
        got = [(r["sku"], r["grade"], r["grip"], r["used_price"], r["in_stock"])
               for r in self.rows]
        self.assertEqual(got, [
            ("UR0C27A", "Grade A", '4 1/4"', 269.0, 1),
            ("UR0C13F", "Grade B", '4 1/4"', 259.0, 1),
            ("UR0C17C", "Grade B", '4 3/8"', 259.0, 1),
            ("UR8A17B", "Grade B", '4 1/2"', 259.0, 1),
            ("UR0C29A", "Grade B", '4 1/2"', 259.0, 1),
            ("UR8A05G", "Grade B", '4 1/2"', 259.0, 1),
            ("UR8A18A", "Grade B", '4 1/2"', 259.0, 1),
        ])

    def test_derived_fields(self):
        r = self.rows[0]
        self.assertEqual(r["discount_pct"], 10)
        self.assertFalse(r["new_cheaper"])
        self.assertEqual((r["code"], r["racquet"], r["url"]),
                         ("WRFPR", "Wilson RF 01 Pro Racquet", "u"))

    def test_specs(self):
        r = self.rows[0]
        self.assertEqual(r["specs"]["head"], "98 in² / 632.26 cm²")
        self.assertEqual(r["specs"]["balance"], "12.75in / 32.39cm / 6 pts HL")
        self.assertEqual(r["nspec"], {
            "head_in2": 98.0, "weight_oz": 11.9, "weight_g": 337.0,
            "swingweight": 331.0, "stiffness": 67.0, "balance_pts": -6.0})

    def test_empty_page_has_no_rows(self):
        self.assertEqual(tw_used.parse_listings("<html></html>",
                                                {"name": "x", "brand": "y",
                                                 "new_price": 1, "code": "c"},
                                                "u"), [])


class NumericSpecsTest(unittest.TestCase):
    def test_head_heavy_is_positive(self):
        n = tw_used.numeric_specs({"balance": "13.2in / 33.5cm / 2 pts HH"})
        self.assertEqual(n["balance_pts"], 2.0)

    def test_missing_specs(self):
        self.assertEqual(tw_used.numeric_specs({}), {})


class JudgeTest(unittest.TestCase):
    ROW = {"racquet": "R", "grade": "Grade B", "sku": "S1"}

    def verdict(self, price, past):
        return tw_used.judge({**self.ROW, "used_price": price},
                             {("R", "Grade B"): past})[0]

    def test_too_little_history(self):
        self.assertEqual(self.verdict(100, [200, 200]), "")

    def test_verdicts(self):
        past = [150, 210, 220, 230]           # median 215, low 150
        self.assertEqual(self.verdict(149, past), "LOWEST EVER")
        self.assertEqual(self.verdict(150, past), "BELOW USUAL")
        self.assertEqual(self.verdict(193, past), "BELOW USUAL")   # <= 90% of 215
        self.assertEqual(self.verdict(194, past), "typical")
        self.assertEqual(self.verdict(215, past), "typical")
        self.assertEqual(self.verdict(237, past), "high")

    def test_marked_down_from(self):
        hist = {"S1": [("2026-09-01", 229.0), ("2026-09-05", 189.0),
                       ("2026-09-06", 139.0)]}
        row = {"sku": "S1", "used_price": 139.0}
        self.assertEqual(tw_used.marked_down_from(row, hist), 189.0)
        self.assertIsNone(tw_used.marked_down_from(
            {"sku": "S1", "used_price": 239.0}, hist))
        self.assertIsNone(tw_used.marked_down_from(
            {"sku": "S2", "used_price": 1.0}, hist))


class DistinctHistoryTest(unittest.TestCase):
    def test_one_listing_counts_once_per_price(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("date,brand,racquet,grade,grip,used_price,new_price,sku\n")
            for d in range(1, 11):              # ten days at one price
                f.write(f"2026-09-{d:02},W,R,Grade B,4,150,300,S1\n")
            f.write("2026-09-11,W,R,Grade B,4,130,300,S1\n")
            f.write("2026-09-11,W,R,Grade B,4,170,300,S2\n")
        try:
            self.assertEqual(sorted(tw_used.load_history(path=f.name)[("R", "Grade B")]),
                             [130, 150, 170])
            self.assertEqual(len(tw_used.load_history(path=f.name, distinct=False)
                                 [("R", "Grade B")]), 12)
            self.assertEqual(tw_used.load_history(before="2026-09-11", path=f.name)
                             [("R", "Grade B")], [150])
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
