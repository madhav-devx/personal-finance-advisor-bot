"""Shared constants. Pure Python - no Flask or database imports."""

APP_NAME = "Personal Finance Advisor Bot"

EXPENSE_CATEGORIES = [
    ("rent", "Rent"),
    ("food", "Food & Dining"),
    ("groceries", "Groceries"),
    ("transport", "Transport"),
    ("utilities", "Utilities"),
    ("education", "Education"),
    ("healthcare", "Healthcare"),
    ("entertainment", "Entertainment"),
    ("shopping", "Shopping"),
    ("business", "Business / Project"),
    ("other", "Other"),
]
CATEGORY_LABELS = dict(EXPENSE_CATEGORIES)

CATEGORY_COLORS = {
    "rent": "#2563eb", "food": "#f59e0b", "groceries": "#16a34a", "transport": "#0ea5e9",
    "utilities": "#8b5cf6", "education": "#14b8a6", "healthcare": "#ef4444",
    "entertainment": "#ec4899", "shopping": "#f97316", "business": "#6366f1", "other": "#94a3b8",
}

PAYMENT_METHODS = [
    ("cash", "Cash"), ("upi", "UPI"), ("debit_card", "Debit card"),
    ("credit_card", "Credit card"), ("net_banking", "Net banking"), ("other", "Other"),
]
PAYMENT_LABELS = dict(PAYMENT_METHODS)

INCOME_SOURCES = [
    ("salary", "Salary"), ("freelance", "Freelance payment"), ("allowance", "Allowance"),
    ("business", "Business"), ("investment", "Investment / interest"), ("gift", "Gift"),
    ("other", "Other"),
]
SOURCE_LABELS = dict(INCOME_SOURCES)

PROFILE_TYPES = [
    ("salaried", "Salaried professional"), ("student", "College student"),
    ("freelancer", "Freelancer"), ("household", "Household manager"),
]
PROFILE_LABELS = dict(PROFILE_TYPES)

CURRENCIES = [("₹", "₹ Indian Rupee"), ("$", "$ US Dollar"), ("€", "€ Euro"), ("£", "£ Pound Sterling")]

# Budget rows use this sentinel in the "category" column for the overall monthly budget.
TOTAL_BUDGET_KEY = "total"

# Essential-ish categories are protected when suggesting budgets; WANTS get trimmed first.
NEEDS = {"rent", "food", "groceries", "transport", "utilities", "education", "healthcare", "business"}
WANTS = {"entertainment", "shopping", "other"}

# Rule-of-thumb maximum share of income per category (percent). General heuristics used
# only to flag unusually high spending - they are not personal advice.
CATEGORY_GUIDE_PCT = {
    "rent": 35, "food": 15, "groceries": 15, "transport": 10, "utilities": 8,
    "education": 10, "healthcare": 7, "entertainment": 8, "shopping": 8,
    "business": 25, "other": 5,
}
PROFILE_GUIDE_OVERRIDES = {
    "student": {"food": 25, "rent": 25, "entertainment": 6, "education": 15},
    "household": {"groceries": 20, "education": 15, "utilities": 10, "healthcare": 8},
    "freelancer": {"business": 30},
}

# Share of (base) income a user is encouraged to save, by profile.
SAVINGS_TARGET_RATE = {"salaried": 0.20, "student": 0.10, "freelancer": 0.25, "household": 0.15}

# Months of essential expenses suggested for an emergency fund (commonly cited range: 3-6).
EMERGENCY_MONTHS = {"salaried": 3, "student": 3, "freelancer": 6, "household": 6}

# Starting-point split of spendable income when there is no history yet (sums to 100).
DEFAULT_BUDGET_WEIGHTS = {
    "rent": 28, "food": 12, "groceries": 12, "transport": 8, "utilities": 8,
    "education": 6, "healthcare": 5, "entertainment": 8, "shopping": 8, "other": 5,
}

CATEGORY_TIPS = {
    "rent": ["Rent is hard to change quickly - consider a roommate, a slightly cheaper area, or renegotiating at renewal."],
    "food": [
        "Plan meals for the week and cook at home more often; set a fixed weekly cap for eating out and delivery.",
        "Carry lunch or snacks on busy days - small daily purchases add up quickly.",
    ],
    "groceries": [
        "Shop with a list, compare unit prices and buy staples in bulk when they are on offer.",
        "Reduce food waste by planning meals around what you already have.",
    ],
    "transport": ["Combine trips, use public transport or carpooling where possible, and compare fuel and ride-hailing costs."],
    "utilities": ["Review subscriptions and plans (mobile, internet, electricity usage) and switch off what you do not use."],
    "education": ["Look for used books, shared resources, scholarships or instalment options before paying in full."],
    "healthcare": ["Check whether generics, insurance or preventive care could lower recurring medical costs."],
    "entertainment": [
        "Set a monthly fun-money limit and pick free or low-cost alternatives for some outings.",
        "Audit streaming and app subscriptions - cancel or rotate the ones you rarely use.",
    ],
    "shopping": ["Use a 48-hour rule for non-essential purchases and unsubscribe from promotional emails."],
    "business": ["Separate business and personal spending and review recurring tools and subscriptions for overlap."],
    "other": ["Categorise 'other' spending more precisely - unexplained spending is the easiest to overlook."],
}

DISCLAIMER = (
    "Insights are educational and based only on the data you entered. They are not "
    "personalised financial, tax or investment advice, and no investment returns are promised."
)
