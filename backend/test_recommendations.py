# Run all tests:
# .\.venv\Scripts\python.exe -m unittest backend.test_recommendations

#Run all tests with test names shown:
# .\.venv\Scripts\python.exe -m unittest -v backend.test_recommendations

import re
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["GEMINI_API_KEY"] = "unit-test-disabled"
os.environ["CANOPY_API_KEY"] = "unit-test-disabled"
os.environ["SCRAPERAPI_KEY"] = "unit-test-disabled"
os.environ["GOOGLE_PLACES_API_KEY"] = "unit-test-disabled"

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
    def setUp(self):
        self.query_patcher = patch.object(
            app_main,
            "build_recommendation_query",
            side_effect=self._default_recommendation_query,
        )
        self.query_builder = self.query_patcher.start()
        self.addCleanup(self.query_patcher.stop)

    def _default_recommendation_query(
        self,
        history,
        filter_mode="overall",
        refinement_prompt="",
        image_data_url="",
    ):
        query = str(refinement_prompt or "").strip()
        if not query:
            query = "popular products"
            for item in history[:8]:
                analysis = item.get("analysis") if isinstance(item, dict) else {}
                if not isinstance(analysis, dict):
                    continue
                candidate = analysis.get("productKeyword") or analysis.get("title")
                if candidate and candidate != "unknown":
                    query = str(candidate)
                    break

        suffix_by_filter = {
            "overall": "best value",
            "durability": "durable reliable",
            "price": "budget affordable deal",
            "quality": "top rated premium",
        }
        terms = [query]
        suffix = suffix_by_filter.get(filter_mode, "best value")
        if suffix and suffix not in query.lower():
            terms.append(f"{query} {suffix}")
        if re.search(r"\blaptops?\b|\bchromebooks?\b|\bnotebooks?\b", query, re.IGNORECASE):
            terms.append("student laptop durable affordable")
        elif re.search(r"\bwater bottles?\b|\btumbler\b|\bbottle\b", query, re.IGNORECASE):
            terms.append("insulated water bottle leakproof")
        elif re.search(r"\bheadphones?\b|\bearbuds?\b|\bairpods?\b", query, re.IGNORECASE):
            terms.append("top rated wireless headphones")

        deduped_terms = []
        for term in terms:
            if term.lower() not in {item.lower() for item in deduped_terms}:
                deduped_terms.append(term)
        return {"query": query, "searchTerms": deduped_terms[:5], "reason": "Test query plan."}

    def test_canopy_search_limits_product_results_for_speed(self):
        session = CapturingSession()

        with (
            patch("backend.marketplaces.amazon_canopy._make_session", return_value=session),
            patch("backend.marketplaces.amazon_canopy._canopy_headers", return_value={"API-KEY": "dummy-test-key"}),
        ):
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

    def test_normalization_rejects_unavailable_marketplace_aliases(self):
        adapter = FakeAdapter("amazon", [])
        product = app_main._normalize_recommendation_product(
            {
                "title": "Sony Noise Cancelling Headphones",
                "asin": "B0UNAVAILABLE",
                "price": {"display": "$99.99", "value": 99.99},
                "availability_message": "Currently unavailable",
            },
            adapter,
        )

        self.assertIsNone(product)

    def test_normalization_keeps_review_count_aliases_for_ranking(self):
        adapter = FakeAdapter("ebay", [])
        product = app_main._normalize_recommendation_product(
            {
                "product_title": "Bluetooth Headphones True Wireless Earbuds",
                "product_url": "https://www.ebay.com/itm/266123456789",
                "item_price": {"value": 19.95, "currency": "USD"},
                "reviews": "1,234",
            },
            adapter,
        )

        self.assertIsNotNone(product)
        self.assertEqual(product["reviewCount"], "1,234")

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

    def test_adapter_order_prefers_recent_history_marketplace(self):
        fake_amazon = FakeAdapter("amazon", [])
        fake_ebay = FakeAdapter("ebay", [])

        with patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]):
            ordered = app_main._ordered_recommendation_adapters("", "ebay")

        self.assertEqual([adapter.name for adapter in ordered], ["ebay", "amazon"])

    def test_nectar_secret_allows_health_but_protects_api_routes(self):
        fake_amazon = FakeAdapter("amazon", [])
        fake_ebay = FakeAdapter("ebay", [])

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", "required-secret"),
        ):
            client = TestClient(app_main.app)
            health = client.get("/health")
            blocked = client.post("/recommendations", json={"history": [], "prompt": "headphones"})
            allowed = client.post(
                "/recommendations",
                headers={"X-Nectar-Secret": "required-secret"},
                json={"history": [], "prompt": "headphones"},
            )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

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

    def test_explicit_laptop_prompt_does_not_search_history_terms(self):
        laptop_query = "durable but cheap laptops for students"
        fake_amazon = FakeAdapter(
            "amazon",
            {
                laptop_query: [],
                "Hydro Flask Water Bottle Insulated": [
                    {
                        "title": "Hydro Flask Water Bottle Insulated",
                        "asin": "B0BOTTLEHISTORY",
                        "price": {"display": "$49.95", "value": 49.95},
                        "rating": 4.6,
                        "ratingsTotal": 8343,
                        "brand": "Hydro Flask",
                    }
                ],
            },
        )
        fake_ebay = FakeAdapter("ebay", {})
        history = [
            {
                "analysis": {
                    "title": "Hydro Flask Water Bottle Insulated",
                    "productKeyword": "Hydro Flask Water Bottle Insulated",
                    "brand": "Hydro Flask",
                    "price": "$49.95",
                }
            }
        ]

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": history, "filter": "overall", "prompt": laptop_query, "marketplace": "all"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"], [])
        self.assertEqual(fake_amazon.calls[0], laptop_query)
        self.assertEqual(fake_ebay.calls[0], laptop_query)
        self.assertNotIn("Hydro Flask Water Bottle Insulated", fake_amazon.calls)
        self.assertNotIn("Hydro Flask Water Bottle Insulated", fake_ebay.calls)
        self.assertGreaterEqual(len(fake_amazon.calls), 2)

    def test_explicit_laptop_prompt_rejects_unrelated_marketplace_results(self):
        fake_amazon = FakeAdapter(
            "amazon",
            [
                {
                    "title": "Hydro Flask Water Bottle Insulated Stainless Steel",
                    "asin": "B0WRONGBOTTLE",
                    "price": {"display": "$49.95", "value": 49.95},
                    "rating": 4.6,
                    "ratingsTotal": 8343,
                    "brand": "Hydro Flask",
                }
            ],
        )
        fake_ebay = FakeAdapter("ebay", [])

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "most popular laptops for students"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["products"], [])

    def test_recommendations_use_gemini_search_terms_for_refined_prompts(self):
        fake_amazon = FakeAdapter(
            "amazon",
            {
                "cheap student laptops": [],
                "student laptop durable affordable": [
                    {
                        "title": "HP Pavilion Student Laptop 16GB RAM 512GB SSD",
                        "asin": "B0SMARTPLAN1",
                        "price": {"display": "$489.99", "value": 489.99},
                        "rating": 4.5,
                        "ratingsTotal": 2400,
                        "brand": "HP",
                    }
                ],
            },
        )
        fake_ebay = FakeAdapter("ebay", {})

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
            patch.object(
                app_main,
                "build_recommendation_query",
                return_value={
                    "query": "cheap student laptops",
                    "searchTerms": ["cheap student laptops", "student laptop durable affordable"],
                    "reason": "Gemini planned a durable student laptop search.",
                },
            ),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": [], "filter": "overall", "prompt": "best durable but cheap laptops for students"},
            )

        self.assertEqual(response.status_code, 200)
        products = response.json()["products"]
        self.assertEqual([product["listingId"] for product in products], ["B0SMARTPLAN1"])
        self.assertIn("student laptop durable affordable", fake_amazon.calls)

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

    def test_recommendations_skip_exact_scan_history_repeats(self):
        fake_amazon = FakeAdapter(
            "amazon",
            [
                {
                    "title": "Hydro Flask Water Bottle 32 Oz Shale Gray",
                    "asin": "B0SCANNEDITEM",
                    "price": {"display": "$49.95", "value": 49.95},
                    "rating": 4.6,
                    "ratingsTotal": 8343,
                    "brand": "Hydro Flask",
                },
                {
                    "title": "Owala FreeSip Insulated Stainless Steel Water Bottle 32 Oz",
                    "asin": "B0FRESHITEM",
                    "price": {"display": "$29.99", "value": 29.99},
                    "rating": 4.7,
                    "ratingsTotal": 12000,
                    "brand": "Owala",
                },
            ],
        )
        fake_ebay = FakeAdapter("ebay", [])
        history = [
            {
                "analysis": {
                    "title": "Hydro Flask Water Bottle 32 Oz Shale Gray",
                    "asin": "B0SCANNEDITEM",
                    "brand": "Hydro Flask",
                    "price": "$49.95",
                    "marketplace": "amazon",
                }
            }
        ]

        with (
            patch.object(app_main, "MARKETPLACE_ADAPTERS", [fake_amazon, fake_ebay]),
            patch.object(app_main, "NECTAR_SECRET", ""),
        ):
            response = TestClient(app_main.app).post(
                "/recommendations",
                json={"history": history, "filter": "overall", "prompt": "best current water bottles"},
            )

        products = response.json()["products"]
        self.assertEqual([product["listingId"] for product in products], ["B0FRESHITEM"])

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
        self.assertFalse(any("Headphones" in title for title in titles))
        self.assertIn("Heartleaf Pore Control Cleansing Oil", fake_ebay.calls)
        self.assertNotIn("headphones", fake_ebay.calls)

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

    def test_price_trend_endpoint_returns_points_and_ai_call(self):
        with (
            patch.object(app_main, "NECTAR_SECRET", ""),
            patch.object(
                app_main,
                "build_price_trend_narrative",
                return_value={
                    "narrative": "Stable with one recent dip.",
                    "likelyToDrop": False,
                    "confidence": 0.62,
                    "callouts": ["Lowest in 30 days"],
                },
            ) as trend_builder,
        ):
            response = TestClient(app_main.app).post(
                "/price-trend",
                json={"analysis": {"title": "Hydro Flask", "price": "$49.95"}},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["points"]), 30)
        self.assertTrue(body["insights"])
        self.assertEqual(body["narrative"], "Stable with one recent dip.")
        trend_builder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
