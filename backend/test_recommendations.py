import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main as app_main
from backend.marketplaces.amazon_canopy import AmazonCanopyAdapter, SEARCH_RESULT_LIMIT
from backend.marketplaces.ebay_scraper import EbayScraperAPIAdapter
from backend.vision_model import clean_similar_products


class FakeAdapter:
    def __init__(self, name, results):
        self.name = name
        self._results = results
        self.calls = []

    def product_url(self, listing_id):
        if self.name == "amazon":
            return f"https://www.amazon.com/dp/{listing_id}"
        return f"https://www.ebay.com/itm/{listing_id}"

    def search_similar_products(self, search_term):
        self.calls.append(search_term)
        if isinstance(self._results, dict):
            return list(self._results.get(search_term, []))
        return list(self._results)


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "data": {
                "amazonProductSearchResults": {
                    "productResults": {
                        "results": [
                            {
                                "title": "Amazon Search Result",
                                "asin": "B0LIMITTEST",
                                "brand": "AmazonBrand",
                                "rating": 4.5,
                                "ratingsTotal": 123,
                                "mainImageUrl": "https://images.amazon.test/item.jpg",
                                "isPrime": True,
                                "price": {"display": "$19.99", "value": 19.99},
                            }
                        ]
                    }
                }
            }
        }


class CapturingSession:
    def __init__(self):
        self.payload = None

    def post(self, _url, *, json, headers, timeout):
        self.payload = json
        return FakeResponse()

    def close(self):
        pass


class RecommendationTests(unittest.TestCase):
    def test_canopy_search_limits_product_results_for_speed(self):
        session = CapturingSession()

        with patch("backend.marketplaces.amazon_canopy._make_session", return_value=session):
            results = AmazonCanopyAdapter().search_similar_products("running shoes")

        self.assertEqual(len(results), 1)
        self.assertIn(f"limit: {SEARCH_RESULT_LIMIT}", session.payload["query"])

    def test_normalizes_ebay_search_shape_with_name_link_and_raw_price(self):
        adapter = FakeAdapter("ebay", [])
        product = app_main._normalize_recommendation_product(
            {
                "name": "Nike Mens Running Shoes Size 10",
                "link": "https://www.ebay.com/itm/Nike-Mens-Running-Shoes/256123456789",
                "current_price": {"raw": "$49.99"},
                "thumbnail": "https://i.ebayimg.test/shoe.jpg",
                "seller_name": "trusted-seller",
                "reviewCount": "1,240",
            },
            adapter,
        )

        self.assertIsNotNone(product)
        self.assertEqual(product["listingId"], "256123456789")
        self.assertEqual(product["price"], "$49.99")
        self.assertEqual(product["priceValue"], 49.99)
        self.assertEqual(product["image"], "https://i.ebayimg.test/shoe.jpg")
        self.assertEqual(product["brand"], "trusted-seller")

    def test_normalizes_nested_and_protocol_relative_recommendation_images(self):
        adapter = FakeAdapter("amazon", [])
        product = app_main._normalize_recommendation_product(
            {
                "title": "SKIN1004 Madagascar Centella Light Cleansing Oil",
                "asin": "B0IMAGEOBJECT",
                "price": {"display": "$12.50", "value": 12.50},
                "image": {"url": "//images.amazon.test/skin1004.jpg"},
            },
            adapter,
        )

        self.assertIsNotNone(product)
        self.assertEqual(product["image"], "https://images.amazon.test/skin1004.jpg")

    def test_ebay_adapter_search_normalizer_preserves_name_title(self):
        adapter = EbayScraperAPIAdapter()
        product = adapter._normalize_search_result(
            {
                "name": "Bluetooth Headphones True Wireless Earbuds",
                "link": "https://www.ebay.com/itm/266123456789",
                "price": {"extracted": 19.95},
                "image_url": "https://i.ebayimg.test/earbuds.jpg",
                "seller": {"username": "audio-store"},
            }
        )

        self.assertEqual(product["title"], "Bluetooth Headphones True Wireless Earbuds")
        self.assertEqual(product["asin"], "266123456789")
        self.assertEqual(product["price"]["display"], "$19.95")
        self.assertEqual(product["brand"], "audio-store")

    def test_ebay_adapter_search_normalizer_flattens_image_objects(self):
        adapter = EbayScraperAPIAdapter()
        product = adapter._normalize_search_result(
            {
                "title": "Roto Grip Bowling Ball",
                "product_url": "https://www.ebay.com/itm/267111111111",
                "price": {"raw": "$53.00"},
                "images": [{"src": "//i.ebayimg.test/ball.jpg"}],
            }
        )

        self.assertEqual(product["mainImageUrl"], "https://i.ebayimg.test/ball.jpg")

    def test_ebay_adapter_search_normalizer_supports_scraperapi_product_fields(self):
        adapter = EbayScraperAPIAdapter()
        product = adapter._normalize_search_result(
            {
                "product_title": "adidas women Adizero EVO SL Shoes",
                "product_url": "https://www.ebay.com/itm/157982251702",
                "item_price": {"value": 68, "currency": "USD"},
                "image": "https://i.ebayimg.test/shoes.jpg",
                "condition": "Brand New",
            }
        )

        self.assertEqual(product["title"], "adidas women Adizero EVO SL Shoes")
        self.assertEqual(product["asin"], "157982251702")
        self.assertEqual(product["listingUrl"], "https://www.ebay.com/itm/157982251702")
        self.assertEqual(product["price"]["display"], "$68.00")
        self.assertEqual(product["brand"], "Adidas")

    def test_ebay_adapter_search_normalizer_prefers_current_price_over_discount_artifact(self):
        adapter = EbayScraperAPIAdapter()
        product = adapter._normalize_search_result(
            {
                "title": "Wolverine Men Floorhand Waterproof Work Boot",
                "link": "https://www.ebay.com/itm/135713766682",
                "price": {"raw": "$8.39"},
                "current_price": {"raw": "US $83.96"},
                "image_url": "https://i.ebayimg.test/boot.jpg",
            }
        )

        self.assertEqual(product["price"]["display"], "$83.96")
        self.assertEqual(product["price"]["value"], 83.96)

    def test_diversify_keeps_all_marketplace_fill_from_collapsing_to_one_source(self):
        ranked_products = [
            {
                "title": f"Amazon Headphones {index}",
                "listingId": f"B0AMZ{index}",
                "marketplace": "amazon",
                "brand": f"AmazonBrand{index}",
                "_sourceTermIndex": 0,
            }
            for index in range(6)
        ] + [
            {
                "title": f"eBay Headphones {index}",
                "listingId": f"26EBAY{index}",
                "marketplace": "ebay",
                "brand": f"EbayBrand{index}",
                "_sourceTermIndex": 0,
            }
            for index in range(6)
        ]

        products = app_main._diversify_recommendations(
            ranked_products,
            limit=5,
            max_per_brand=10,
            max_per_marketplace=4,
        )

        self.assertEqual(len(products), 5)
        self.assertIn("ebay", {product["marketplace"] for product in products})

    def test_recommendations_endpoint_returns_products_from_stubbed_marketplaces(self):
        fake_ebay = FakeAdapter(
            "ebay",
            [
                {
                    "name": "Nike Mens Running Shoes Lightweight Trainer",
                    "link": "https://www.ebay.com/itm/256123456789",
                    "currentPrice": {"raw": "$54.00"},
                    "rating": 4.6,
                    "reviewCount": "860",
                    "thumbnailUrl": "https://i.ebayimg.test/nike.jpg",
                    "seller_name": "run-shop",
                }
            ],
        )
        fake_amazon = FakeAdapter(
            "amazon",
            [
                {
                    "title": "Nike Mens Running Shoes Road Running Sneaker",
                    "asin": "B0TESTSHOE",
                    "price": {"display": "$64.99", "value": 64.99},
                    "rating": 4.7,
                    "ratingsTotal": 1200,
                    "mainImageUrl": "https://images.amazon.test/shoe.jpg",
                    "brand": "Nike",
                    "isPrime": True,
                }
            ],
        )

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "nike mens running shoes"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(len(body["products"]), 2)
        self.assertTrue(all(product.get("listingId") for product in body["products"]))
        self.assertTrue(all(product.get("price") for product in body["products"]))

    def test_recommendations_chat_prompt_respects_ebay_only_lock(self):
        fake_ebay = FakeAdapter(
            "ebay",
            [
                {
                    "name": "Bluetooth Headphones True Wireless Earbuds",
                    "link": "https://www.ebay.com/itm/266123456789",
                    "price": {"raw": "$19.95"},
                    "rating": 4.4,
                    "reviews": "312",
                    "image_url": "https://i.ebayimg.test/earbuds.jpg",
                }
            ],
        )
        fake_amazon = FakeAdapter(
            "amazon",
            [
                {
                    "title": "Bluetooth Headphones True Wireless Earbuds",
                    "asin": "B0AMAZONHEADPHONES",
                    "price": {"display": "$24.99", "value": 24.99},
                }
            ],
        )

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={
                    "history": [],
                    "filter": "overall",
                    "prompt": "find bluetooth headphones on ebay only",
                },
            )

        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["marketplace"], "ebay")
        self.assertEqual(products[0]["listingId"], "266123456789")

    def test_recommendations_chat_prompt_handles_scraperapi_ebay_shape(self):
        fake_ebay = FakeAdapter(
            "ebay",
            [
                {
                    "product_title": "adidas women Adizero EVO SL Shoes",
                    "product_url": "https://www.ebay.com/itm/157982251702",
                    "item_price": {"value": 68, "currency": "USD"},
                    "image": "https://i.ebayimg.test/shoes.jpg",
                }
            ],
        )
        fake_amazon = FakeAdapter("amazon", [])

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "running shoes"},
            )

        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["title"], "adidas women Adizero EVO SL Shoes")
        self.assertEqual(products[0]["listingId"], "157982251702")
        self.assertEqual(products[0]["brand"], "Adidas")

    def test_recommendations_amazon_marketplace_skips_ebay_when_enough(self):
        amazon_results = [
            {
                "title": f"Nike Running Shoes Amazon Option {index}",
                "asin": f"B0AMAZON{index:03d}",
                "price": {"display": f"${60 + index}.99", "value": 60 + index},
                "rating": 4.5,
                "ratingsTotal": 1000 + index,
                "mainImageUrl": f"https://images.amazon.test/shoe-{index}.jpg",
                "brand": "Nike",
                "isPrime": index % 2 == 0,
            }
            for index in range(6)
        ]
        ebay_results = [
            {
                "product_title": "Nike Running Shoes eBay Backup",
                "product_url": "https://www.ebay.com/itm/157982251702",
                "item_price": {"value": 45, "currency": "USD"},
            }
        ]
        fake_amazon = FakeAdapter("amazon", amazon_results)
        fake_ebay = FakeAdapter("ebay", ebay_results)

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "running shoes", "marketplace": "amazon"},
            )

        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual(len(products), 5)
        self.assertTrue(all(product["marketplace"] == "amazon" for product in products))
        self.assertEqual(fake_amazon.calls, ["running shoes"])
        self.assertEqual(fake_ebay.calls, [])

    def test_recommendations_all_marketplace_can_include_both_sources(self):
        amazon_results = [
            {
                "title": f"Amazon Headphones Option {index}",
                "asin": f"B0ALLAMZ{index:03d}",
                "price": {"display": f"${40 + index}.99", "value": 40 + index},
                "rating": 4.5,
                "ratingsTotal": 1000 + index,
                "brand": "Sony",
            }
            for index in range(6)
        ]
        ebay_results = [
            {
                "product_title": f"eBay Headphones Option {index}",
                "product_url": f"https://www.ebay.com/itm/15798225170{index}",
                "item_price": {"value": 20 + index, "currency": "USD"},
            }
            for index in range(6)
        ]
        fake_amazon = FakeAdapter("amazon", amazon_results)
        fake_ebay = FakeAdapter("ebay", ebay_results)

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "headphones", "marketplace": "all"},
            )

        marketplaces = [product["marketplace"] for product in response.json()["products"]]
        self.assertIn("amazon", marketplaces)
        self.assertIn("ebay", marketplaces)

    def test_recommendations_marketplace_filter_controls_sources(self):
        amazon_results = [
            {
                "title": "Amazon Headphones",
                "asin": "B0AMAZONFILTER",
                "price": {"display": "$49.99", "value": 49.99},
                "rating": 4.6,
                "ratingsTotal": 5000,
                "brand": "Sony",
            }
        ]
        ebay_results = [
            {
                "product_title": "eBay Headphones",
                "product_url": "https://www.ebay.com/itm/157982251702",
                "item_price": {"value": 29.99, "currency": "USD"},
            }
        ]
        fake_amazon = FakeAdapter("amazon", amazon_results)
        fake_ebay = FakeAdapter("ebay", ebay_results)

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            amazon_response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "headphones", "marketplace": "amazon"},
            )
            ebay_response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "headphones", "marketplace": "ebay"},
            )

        amazon_products = amazon_response.json()["products"]
        ebay_products = ebay_response.json()["products"]
        self.assertEqual([product["marketplace"] for product in amazon_products], ["amazon"])
        self.assertEqual([product["marketplace"] for product in ebay_products], ["ebay"])

    def test_recent_history_products_win_over_stale_fast_history_terms(self):
        heartleaf_results = [
            {
                "name": f"Heartleaf Pore Control Cleansing Oil Option {index}",
                "link": f"https://www.ebay.com/itm/26700000000{index}",
                "price": {"raw": f"${12 + index}.99"},
                "rating": 4.2 + (index / 10),
                "reviews": f"{100 + index}",
                "image_url": f"https://i.ebayimg.test/heartleaf-{index}.jpg",
            }
            for index in range(6)
        ]
        stale_headphone_results = [
            {
                "name": "Bluetooth Headphones True Wireless Earbuds",
                "link": "https://www.ebay.com/itm/266123456789",
                "price": {"raw": "$19.95"},
                "rating": 5.0,
                "reviews": "9000",
            }
        ]
        fake_ebay = FakeAdapter(
            "ebay",
            {
                "Heartleaf Pore Control Cleansing Oil": heartleaf_results,
                "headphones": stale_headphone_results,
                "Bluetooth Headphones True Wireless Earbuds": stale_headphone_results,
            },
        )
        fake_amazon = FakeAdapter("amazon", {})
        history = [
            {
                "id": "current",
                "analysis": {
                    "title": "Heartleaf Pore Control Cleansing Oil",
                    "productKeyword": "Heartleaf Pore Control Cleansing Oil",
                    "marketplace": "amazon",
                },
            },
            {
                "id": "old",
                "analysis": {
                    "title": "Bluetooth Headphones True Wireless Earbuds",
                    "productKeyword": "headphones",
                    "marketplace": "amazon",
                },
            },
        ]

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": history, "filter": "overall", "prompt": ""},
            )

        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual(len(products), 5)
        titles = [product["title"] for product in products]
        self.assertTrue(any("Heartleaf" in title for title in titles))
        self.assertTrue(any("Headphones" in title for title in titles))
        self.assertLess(
            min(index for index, title in enumerate(titles) if "Heartleaf" in title),
            min(index for index, title in enumerate(titles) if "Headphones" in title),
        )
        self.assertIn("Heartleaf Pore Control Cleansing Oil", fake_ebay.calls)
        self.assertIn("headphones", fake_ebay.calls)

    def test_similar_products_cleaner_keeps_valid_adapter_results(self):
        cleaned = clean_similar_products(
            [
                {"asin": "ORIGINAL", "title": "Original Headphones"},
                {"asin": "B0EARBUDS1", "title": "Wireless Earbuds with Charging Case"},
                {"asin": "B0EARBUDS1", "title": "Wireless Earbuds with Charging Case"},
                {"asin": "B0CASEONLY", "title": "Protective Silicone Case Cover"},
            ],
            "ORIGINAL",
            "Bluetooth Headphones True Wireless Earbuds",
        )

        self.assertEqual([item["asin"] for item in cleaned], ["B0EARBUDS1"])


if __name__ == "__main__":
    unittest.main()
