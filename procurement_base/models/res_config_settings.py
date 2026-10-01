from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    pr_ceo_approval_threshold = fields.Float(
        string='PR CEO Approval Threshold',
        default=100000.0,
        help="Local Purchase Requisitions with total amount below this threshold will skip CEO approval."
    )
    rfq_threshold_from = fields.Float(
        string='RFQ Threshold From',
        default=0.0,
        help="Minimum total amount required to create an RFQ."
    )
    rfq_threshold_to = fields.Float(
        string='RFQ Threshold To',  
        default=1000000.0,
        help="Maximum total amount allowed to create an RFQ."
    )
    lc_expiry_days = fields.Integer(
        string='LC Validity (Days)',
        default=180,
        help="Number of days from the LC issue date until it expires. Used to auto-compute the expiry date."
    )
    lc_alert_days = fields.Integer(
        string='LC Expiry Alert (Days)',
        default=30,
        help="Number of days before expiry to show an alert warning on the LC form."
    )
    set_po_date_as_receipt_date = fields.Boolean(
        string="Set PO Expected Arrival Date as Receipt Date",
        default=True,
        help="When enabled, incoming receipts generated from Purchase Orders will default their scheduled date to the PO expected arrival date."
    )

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pr_ceo_approval_threshold = fields.Float(
        related='company_id.pr_ceo_approval_threshold',
        readonly=False,
        string='PR CEO Approval Threshold'
    )
    rfq_threshold_from = fields.Float(
        related='company_id.rfq_threshold_from',
        readonly=False,
        string='RFQ Threshold From'
    )
    rfq_threshold_to = fields.Float(
        related='company_id.rfq_threshold_to',
        readonly=False,
        string='RFQ Threshold To'
    )
    lc_expiry_days = fields.Integer(
        related='company_id.lc_expiry_days',
        readonly=False,
        string='LC Validity (Days)',
    )
    lc_alert_days = fields.Integer(
        related='company_id.lc_alert_days',
        readonly=False,
        string='LC Expiry Alert (Days)',
    )
    set_po_date_as_receipt_date = fields.Boolean(
        related='company_id.set_po_date_as_receipt_date',
        readonly=False,
        string="Set PO Expected Arrival Date as Receipt Date"
    )