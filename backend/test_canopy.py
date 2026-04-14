# test_canopy.py
from canopy_client import get_full_product_profile, search_similar_products
                                                # B0DKD54S65 <-- blue light glasses -> WORKS WITH ANY LINK !
                                                # B01LXC1QL0 <-- Razer Deathhadder Elite -> I want the reddit PRAW api to track this as BAD.
result = get_full_product_profile("B0DKD54S65")  # test ASIN B0B3JBVDYP 
print("Title:", result["product"].get("title"))
print("Rating:", result["product"].get("rating"))
print("Reviews found:", len(result["reviews"]))
print("First review:", result["reviews"][0] if result["reviews"] else "none")

# --- new search test ---
# Simulates what happens after CLIP identifies "wireless headphones" from a screenshot
similar = search_similar_products("wireless headphones", max_price=150.0)
print(f"\nFound {len(similar)} similar products:")
for p in similar[:3]:   # print first 3 to keep it readable
    print(f"  - {p['title']} | {p['price']['display']} | ⭐ {p['rating']}")