# -*- coding: utf-8 -*-
{
    'name': 'IBMS Sales Return',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Sales Return Workflow: Return Orders with Approval, Return Invoices (Credit Notes), and Dedicated "Returned from Sales" Receipts',
    'description': """
IBMS Sales Return Module:
- "Return Sale" button on Sales Order opening an item-selection return wizard.
- Creates dedicated Return Sales Orders linked to the original order.
- Passes quotation approval workflow (Draft -> Waiting Approval -> Return Confirmed).
- Automatically creates draft Return Delivery (incoming receipt) under dedicated "Returned from Sales" Operation Type for storekeeper receipt.
- "Create Return Invoice" button generating Customer Credit Note (out_refund) linked to original invoice.
- Complete audit trail with smart buttons for Returns, Deliveries, and Invoices.
    """,
    'author': 'IBMS',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'sale',
        'sale_stock',
        'account',
        'ibms_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_data.xml',
        'wizard/sale_order_return_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/stock_warehouse_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
