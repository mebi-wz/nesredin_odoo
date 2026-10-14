# -*- coding: utf-8 -*-
{
    'name': 'IBMS Sales Customizations',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Quotation Approvals, Cash/Credit Sales, Global Discounts, Order Line Part Numbers, Customer Credit Management',
    'description': """
IBMS Sales Customizations:
- Quotation / Sales Order Approval Workflow (Draft -> Waiting Approval -> Sale)
- Cash Sales vs Credit Sales with payment proof & payment note
- Customer Credit Management with Warning & Blocking thresholds
- Global Order Discount (Option B virtual calculation with invoice integration)
- 5% salesperson discount limit with Manager Approval enforcement
- Quotation Order Lines: Real-time Part Number auto-population
- Cash Sales, Credit Sales, and Approval tree views, filters, and menus
    """,
    'author': 'IBMS',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_stock', 'account', 'base_accounting_kit', 'ibms_product'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/sale_order_reject_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/credit_management_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
