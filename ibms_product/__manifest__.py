# -*- coding: utf-8 -*-
{
    'name': 'IBMS Product Customizations',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Rename Reference to Product Code, enforce uniqueness, and add Product Part Number',
    'description': """
IBMS Product Customizations:
- Relabels Internal Reference to "Product Code"
- Enforces uniqueness on Product Code
- Adds "Product Part Number" field to products
    """,
    'author': 'IBMS',
    'license': 'LGPL-3',
    'depends': ['product', 'stock'],
    'data': [
        'views/product_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
