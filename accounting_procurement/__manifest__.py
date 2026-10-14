{
    "name": "Accounting Procurement",
    "version": "19.0.1.0",
    "category": "Accounting",
    "summary": "Integration of Procurement Menus into Accounting",
    "author": "Droga Consulting",
    "depends": [
        "account",
        "procurement_base",
        "procurement_foreign_operations",
        "procurement_local_purchase",
        "procurement_foreign_purchase",
        "procurement_foreign_rfq",
        "sale",
        "stock",
    ],
    "data": [
        "views/accounting_menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
