{
    "name": "Store Requisitions",
    "version": "19.0.1.4",
    "category": "Inventory/Procurement",
    "summary": "Internal store requisition for procurement",
    "author": "Consulting",
    "depends": [
        "procurement_base",
        "base_account_budget",
    ],
    "data": [
        "data/store_sequences.xml",
        "security/store_requisition_security.xml",
        "security/store_requisition_rules.xml",
        "security/ir.model.access.csv",
        "wizard/store_shortage_wizard_views.xml",
        "views/procurement_store_requisition_views.xml",
        "views/procurement_store_requisition_actions.xml",
        "views/procurement_store_requisition_menus.xml",
    ],
    "demo": [
        "demo/store_requisition_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
