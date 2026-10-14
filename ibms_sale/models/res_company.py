# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_sale_withholding_tax = fields.Boolean(
        string="Apply Withholding Tax on Sales",
        default=True,
        help="If enabled, Withholding Tax is automatically applied when the quotation/order subtotal meets or exceeds the threshold.",
    )
    sale_withholding_tax_id = fields.Many2one(
        'account.tax',
        string="Withholding Tax",
        domain=[('type_tax_use', '=', 'sale')],
        default=lambda self: self._default_sale_withholding_tax_id(),
        help="Tax record used for sales withholding tax deduction (e.g. 3% WH).",
    )
    sale_withholding_tax_threshold = fields.Float(
        string="Withholding Tax Threshold",
        default=20000.0,
        help="Minimum sales order subtotal required to trigger withholding tax deduction.",
    )

    @api.model
    def _default_sale_withholding_tax_id(self):
        return self.env['account.tax'].search([
            ('name', '=', '3% WH'),
            ('type_tax_use', '=', 'sale'),
        ], limit=1)
