{
    "name": "Procurement Base",
    "version": "19.0.1.5",
    "category": "Hidden",
    "summary": "Base module for shared procurement menus and resources",
    "author": "Consulting",
    "depends": [
        "base",
        "purchase",
        "purchase_stock",
        "stock",
        "hr"
    ],

    "data": [
        "data/purchase_order_sequences.xml",
        "views/procurement_po_views.xml",
        "views/procurement_po_menus.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],

    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
