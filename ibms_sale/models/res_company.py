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

    top_buyers_limit_n = fields.Integer(
        string="Top N Buyers Count",
        default=10,
        help="Default number of top buyers to rank (e.g. 10)."
    )
    top_buyers_default_metric = fields.Selection([
        ('value', 'Sales Value (Untaxed Subtotal)'),
        ('volume', 'Sales Volume (Total Units)'),
        ('revenue', 'Revenue (Gross Total)'),
    ], string="Top Buyers Ranking Metric", default='value',
       help="Metric used to rank customers: Sales Volume (Units), Sales Value (Untaxed), or Revenue (Gross).")

    top_buyers_default_period = fields.Selection([
        ('this_month', 'This Month'),
        ('this_quarter', 'This Quarter'),
        ('this_year', 'This Year'),
        ('today', 'Today'),
        ('this_week', 'This Week'),
    ], string="Top Buyers Default Period", default='this_month')

    @api.constrains('top_buyers_limit_n')
    def _check_top_buyers_limit_n(self):
        for company in self:
            if company.top_buyers_limit_n < 1:
                raise models.ValidationError("Top N Buyers Count must be at least 1.")

    @api.model
    def _default_sale_withholding_tax_id(self):
        return self.env['account.tax'].search([
            ('name', '=', '3% WH'),
            ('type_tax_use', '=', 'sale'),
        ], limit=1)

