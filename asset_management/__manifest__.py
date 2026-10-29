{
    'name': 'Asset',
    'version': '19.0.1.0.0',
    'author': 'Nesredin',
    'website': 'https://nesredin.com',
    'category': 'Inventory',
    'summary': 'Manage assets with tag numbers, assignment, and warehouse tracking',
    'description': """
Asset Management System
- Tag number generation & tracking
- Asset assignment
- Inventory tracking
- Vehicle tracking
""",
    'depends': ['base', 'hr', 'stock', 'account', 'base_accounting_kit'],
    'data': [
        'data/asset_actions.xml',
        'security/groups.xml',
        'security/record_rules.xml',
        'security/ir.model.access.csv',
        'views/asset_category_views.xml',
        'views/asset_minor_category_views.xml',
        'views/asset_qr_config_views.xml',
        'views/employee_asset_views.xml',
        'views/asset_transaction_wizard_view.xml',
        'views/asset_request_reject_wizard_views.xml',
        'views/asset_views.xml',
        'views/asset_transaction_views.xml',
        'views/asset_vehicle_views.xml',
        'views/asset_warehouse_views.xml',
        'views/asset_location_views.xml',
        'views/asset_warehouse_stock_views.xml',
        'views/asset_specification.xml',
        'views/hr_employee_asset.xml',
        'views/asset_handover_request.xml',
        'views/asset_temporary_request_views.xml',
        'views/account_asset_views_inherit.xml',
        'views/asset_menus.xml',
        'data/ir_sequence_data.xml',
        'reports/asset_handover_report.xml',
        'reports/asset_store_request_report.xml',
        'reports/asset_tag_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'asset_management/static/src/css/asset_dashboard.css',
            'asset_management/static/src/js/asset_dashboard.js',
            'asset_management/static/src/xml/asset_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
