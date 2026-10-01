{
    "name": "Local RFQ",
    "version": "19.0.1.3",
    "category": "Inventory/Procurement",
    "summary": "Local Request for Quotation for procurement process",
    "author": "Consulting",
    "depends": [
        "procurement_base",
        "procurement_local_purchase",
    ],
    "data": [
        "security/local_rfq_security.xml",
        "security/local_rfq_record_rule.xml",
        "security/ir.model.access.csv",
        "data/local_rfq_data.xml",
        "views/local_rfq_views.xml",
        "views/local_purchase_requisition_views.xml",
        "views/local_rfq_actions.xml",
        "views/local_rfq_po_views.xml",
        "views/local_rfq_menus.xml",
        "views/local_rfq_report_action.xml",
        "views/local_rfq_report_template.xml",

    ],
    "demo": [
        "demo/local_rfq_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
