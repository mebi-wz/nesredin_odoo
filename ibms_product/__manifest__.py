# -*- coding: utf-8 -*-
{
    'name': 'IBMS Product & Inventory Customizations',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Product Code, Part Number, Wholesale Price, Warehouse Analytics, Location Transfers, and Warehouse User Access',
    'description': """
IBMS Product & Inventory Customizations:
- Relabels Internal Reference to "Product Code"
- Enforces uniqueness on Product Code
- Adds "Product Part Number" and "Wholesale Price" to products
- Primary and secondary product image support
- Adds "Analytics" tab to Warehouse configuration
- Links Warehouse/Shop to customer invoices for automated branch analytics
- Dedicated stock.location.transfer model and views with Draft -> Submitted -> Approved lifecycle
- Warehouse-level user role and access restrictions
    """,
    'author': 'IBMS',
    'license': 'LGPL-3',
    'depends': ['product', 'stock', 'account', 'analytic'],
    'data': [
        'security/ir.model.access.csv',
        'security/warehouse_security.xml',
        'data/ir_sequence_data.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
        'views/stock_warehouse_views.xml',
        'views/account_move_views.xml',
        'views/res_users_views.xml',
        'views/stock_location_transfer_views.xml',
        'views/stock_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
