# -*- coding: utf-8 -*-
{
    'name': 'Custom Bank Reconciliation & Dashboard Extensions',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Adds Unreconciled Amounts view to bank journals on dashboard and fixes payment link wizard.',
    'author': '',
    'depends': [
        'account',
        'base_accounting_kit',
        'account_reconcile_oca',
        'custom_hc_account_fiscal_period',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/account_journal_dashboard_view.xml',
        'views/account_bank_reconciliation_wizard_views.xml',
        'views/account_bank_reconciliation_period_views.xml',
        'views/account_payment_method_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
