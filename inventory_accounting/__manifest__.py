{
    "name": "Inventory Accounting Integration",
    "version": "19.0.1.0.0",
    "category": "Inventory/Accounting",
    "summary": "Custom Accounting Moves for Inventory",
    "description": """
        Separate module to handle custom stock account/journal entry movement:
        - Automatically creates journal entries on storable product receipts.
        - Inherits Product Category, Stock Move, Account Move, and Account Move Line.
    """,
    "author": "Consulting",
    "depends": [
        "account",
        "stock_account",
        "hr",
    ],
    "data": [
        "security/record_rules.xml",
        "views/product_category_views.xml",
        "views/inventory_valuation_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "OEEL-1",
}
