"""Small, dependency-free category inference for quick transaction entry."""


def infer_category(item: str, description: str = "") -> str:
    text = f"{item} {description}".casefold()
    categories = {
        "Food": [
            "food", "restaurant", "cafe", "coffee", "lunch", "dinner", "breakfast",
            "groceries", "grocery", "zomato", "swiggy", "delivery", "meal", "eat",
            "snack", "drink", "water", "juice", "ice cream", "icecream", "dessert",
            "cake", "chocolate", "pizza", "burger", "sandwich", "mamma", "banana",
            "naan", "shwarma", "shawarma", "guava", "kairi", "sadqa bread",
        ],
        "Transport": [
            "uber", "ola", "taxi", "cab", "auto", "metro", "bus", "train", "fuel",
            "petrol", "diesel", "parking", "toll", "transport", "travel", "flight", "ticket",
        ],
        "Shopping": [
            "amazon", "flipkart", "shopping", "clothes", "clothing", "shoes", "shirt",
            "pants", "dress", "electronics", "phone", "laptop", "gadget", "accessory",
            "bag", "watch", "jewelry", "cosmetic", "makeup", "skincare", "lip balm",
        ],
        "Entertainment": [
            "movie", "cinema", "theatre", "netflix", "prime", "hotstar", "spotify",
            "subscription", "game", "gaming", "concert", "event", "party", "club", "bar",
            "pub", "entertainment", "turf", "sports", "football", "cricket", "tennis",
            "badminton", "gym", "fitness",
        ],
        "Health": [
            "medicine", "pharmacy", "doctor", "hospital", "clinic", "medical", "health",
            "dental", "eye", "checkup", "test", "lab", "insurance", "yoga", "therapy",
        ],
        "Utilities": [
            "electricity", "water bill", "gas bill", "internet", "wifi", "broadband",
            "phone bill", "recharge", "utility", "bill", "rent", "maintenance",
        ],
        "Education": [
            "course", "book", "education", "learning", "training", "certification", "udemy",
            "coursera", "workshop", "seminar",
        ],
        "Personal": [
            "haircut", "salon", "spa", "grooming", "personal", "gift", "donation", "charity",
            "pet", "veterinary",
        ],
    }

    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "Other"
