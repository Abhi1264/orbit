import math
import random
from dataclasses import dataclass

CATEGORIES: dict[str, dict] = {
    "fashion": {
        "share": 0.45,
        "subcategories": [
            "tshirts",
            "shirts",
            "dresses",
            "jeans",
            "kurtas",
            "jackets",
            "activewear",
        ],
        "price": (499, 3499),
        "return_rate": 0.14,
        "brands": [
            "Lumen",
            "Arbor & Vale",
            "Kestrel",
            "Hollow Pine",
            "Marigold Co.",
            "Nightjar",
            "Veld",
        ],
    },
    "footwear": {
        "share": 0.20,
        "subcategories": ["sneakers", "sandals", "running", "formal", "boots"],
        "price": (899, 6999),
        "return_rate": 0.17,
        "brands": ["Stride", "Kestrel", "Northline", "Pace & Co.", "Terrafirm"],
    },
    "accessories": {
        "share": 0.20,
        "subcategories": ["bags", "watches", "sunglasses", "belts", "jewellery"],
        "price": (299, 5999),
        "return_rate": 0.06,
        "brands": ["Lumen", "Halcyon", "Marigold Co.", "Orbit", "Sable"],
    },
    "beauty": {
        "share": 0.15,
        "subcategories": ["skincare", "makeup", "haircare", "fragrance"],
        "price": (199, 2499),
        "return_rate": 0.04,
        "brands": ["Glow Theory", "Halcyon", "Petal", "Ferrous", "Sable"],
    },
}

_SINGULAR = {
    "tshirts": "T-shirt",
    "shirts": "Shirt",
    "dresses": "Dress",
    "jeans": "Jeans",
    "kurtas": "Kurta",
    "jackets": "Jacket",
    "activewear": "Activewear",
    "sneakers": "Sneakers",
    "sandals": "Sandals",
    "running": "Running Shoe",
    "formal": "Formal Shoe",
    "boots": "Boots",
    "bags": "Bag",
    "watches": "Watch",
    "sunglasses": "Sunglasses",
    "belts": "Belt",
    "jewellery": "Jewellery",
    "skincare": "Skincare",
    "makeup": "Makeup",
    "haircare": "Haircare",
    "fragrance": "Fragrance",
}

_ADJECTIVES = [
    "Classic",
    "Relaxed",
    "Slim",
    "Essential",
    "Weekend",
    "Studio",
    "Heritage",
    "Core",
    "Urban",
    "Coastal",
]
_COLOURS = ["Black", "Ivory", "Navy", "Olive", "Rust", "Sand", "Charcoal", "Sage", "Plum", "Stone"]

SEARCH_QUERIES: dict[str, list[str]] = {
    "fashion": [
        "black dress",
        "oversized tshirt",
        "linen shirt",
        "kurta set",
        "denim jacket",
        "joggers",
    ],
    "footwear": ["white sneakers", "running shoes", "sandals men", "formal shoes", "chelsea boots"],
    "accessories": [
        "tote bag",
        "analog watch",
        "aviator sunglasses",
        "leather belt",
        "hoop earrings",
    ],
    "beauty": [
        "vitamin c serum",
        "matte lipstick",
        "hair serum",
        "perfume women",
        "sunscreen spf 50",
    ],
}

@dataclass(frozen=True)
class ProductRow:
    id: int
    sku: str
    name: str
    brand: str
    category: str
    subcategory: str
    price: float
    stock_units: int
    popularity: float

def generate_products(rng: random.Random, count: int) -> list[ProductRow]:
    products: list[ProductRow] = []
    pid = 1
    for category, spec in CATEGORIES.items():
        n = round(count * spec["share"])
        lo, hi = spec["price"]
        for _ in range(n):
            sub = rng.choice(spec["subcategories"])
            brand = rng.choice(spec["brands"])
            price = round(math.exp(rng.uniform(math.log(lo), math.log(hi))) / 10) * 10 - 1
            # Zipf-ish popularity: a few products carry most of the demand.
            popularity = rng.paretovariate(1.2)
            name = f"{brand} {rng.choice(_ADJECTIVES)} {_SINGULAR[sub]} — {rng.choice(_COLOURS)}"
            products.append(
                ProductRow(
                    id=pid,
                    sku=f"TL-{category[:3].upper()}-{pid:05d}",
                    name=name,
                    brand=brand,
                    category=category,
                    subcategory=sub,
                    price=float(price),
                    stock_units=rng.randint(40, 900),
                    popularity=popularity,
                )
            )
            pid += 1
    return products

def apply_stockout_risk(rng: random.Random, products: list[ProductRow], count: int = 18) -> list[ProductRow]:
    """Give the most popular products stock levels that will not cover recent velocity."""
    by_pop = sorted(products, key=lambda p: p.popularity, reverse=True)
    risky = {p.id for p in by_pop[2:45] if rng.random() < 0.5}
    out = []
    picked = 0
    for p in products:
        if p.id in risky and picked < count:
            picked += 1
            out.append(ProductRow(**{**p.__dict__, "stock_units": rng.randint(2, 14)}))
        else:
            out.append(p)
    return out
