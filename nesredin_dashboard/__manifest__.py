{
    "name": "Nesredin Modern Dashboard",
    "version": "19.0.1.0.0",
    "category": "Productivity/Dashboard",
    "summary": "Modern executive operational dashboard with asset management and customization visibility",
    "author": "Droga Consulting / Nesredin",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "sale",
        "purchase",
        "stock",
        "account",
        "hr",
        "asset_management",
        "accounting_procurement",
    ],
    "data": [
        "views/dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "nesredin_dashboard/static/src/js/dashboard.js",
            "nesredin_dashboard/static/src/xml/dashboard.xml",
            "nesredin_dashboard/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
}
