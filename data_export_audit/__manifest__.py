# -*- coding: utf-8 -*-
{
    'name': 'Data Export Audit Logging',
    'version': '19.0.1.0.0',
    'category': 'Administration / Security',
    'summary': 'Track and audit user-initiated data exports (Excel & CSV) with user, records, fields, and timestamp (NSP-14)',
    'description': """
Data Export Audit Logging (NSP-14)
==================================
Maintains an immutable, centralized audit trail of all user-initiated data exports in Odoo.
* Tracks who exported data, when it occurred, and from what IP address.
* Identifies what type of business data was exported (Sales, Customers, Accounting, Inventory, etc.).
* Records the exact record count, export format (Excel / CSV), and all exported column names.
* Preserves active search filters / domains applied at the time of export.
* Provides administrator dashboards and filterable audit views for compliance and security oversight.
    """,
    'author': 'Skylink Technologies',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/data_export_audit_log_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
