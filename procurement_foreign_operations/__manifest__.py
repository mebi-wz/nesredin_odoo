{
    "name": "Foreign Operation",
    "version": "19.0.1.4",
    "category": "Inventory/Procurement",
    "summary": "Foreign procurement operations: ordering, shipment, clearance, and payment requests",
    "author": "Consulting",
    "depends": [
        "procurement_base",
        "procurement_foreign_rfq",
        "stock_landed_costs",
    ],
    "data": [
        "security/foreign_operations_security.xml",
        "security/ir.model.access.csv",
        "data/foreign_operations_data.xml",
        "views/foreign_operations_views.xml",
        "views/foreign_lc_views.xml",
        "views/foreign_payment_request_views.xml",
        "views/foreign_operations_actions.xml",
        "views/foreign_operations_menus.xml",
    ],

    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
