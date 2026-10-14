{
    'name': 'Fiscal Year Periods',
    'version': '19.0.2.3.1',
    'category': 'Accounting/Accounting',
    'summary': 'Structured sub-periods on Fiscal Years with locking to enforce financial period-close rules',
    'description': """
Fiscal Year Periods
====================
Extends the Fiscal Year (account.fiscal.year, provided in this Community
install by the `om_fiscal_year` module) with a Periods sub-table, e.g. 12
monthly periods, each of which can carry a local calendar description
(Ethiopian month names such as Hamle 2018, Nehase 2018, ...).

Key features:
-------------
* Period states: Draft -> Open -> Closed, tracked with a full audit log (chatter)
* Once a period is Closed:
    - Journal entries dated inside it can no longer be posted, reset to
      draft, or edited while posted
    - Stock moves (receipts, deliveries, internal transfers) dated inside
      it can no longer be validated -- regardless of Manual or Automated
      inventory valuation
* Correcting a closed period is a deliberate, logged action: an Accounting
  Manager must re-open it, make the fix, then close it again
* Wizard to auto-generate periods (12/6/4/3/2/1 per year) with optional
  custom names, one per line
* Dedicated "Fiscal Periods" menu for cross-year review

This gives you formal month-end close control similar to the old
account.period model, without touching Odoo's core accounting logic.
    """,
    'author': 'Rise Consulting',
    'depends': ['account', 'om_fiscal_year', 'stock', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/generate_periods_wizard_views.xml',
        'views/account_fiscal_period_views.xml',
        'views/account_fiscal_year_views.xml',
        'views/account_fiscal_year_tree_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
