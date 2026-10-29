# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_sale_withholding_tax = fields.Boolean(
        related='company_id.enable_sale_withholding_tax',
        readonly=False,
        string="Apply Withholding Tax on Sales",
    )
    sale_withholding_tax_id = fields.Many2one(
        'account.tax',
        related='company_id.sale_withholding_tax_id',
        readonly=False,
        string="Withholding Tax",
        domain=[('type_tax_use', '=', 'sale')],
    )
    sale_withholding_tax_threshold = fields.Float(
        related='company_id.sale_withholding_tax_threshold',
        readonly=False,
        string="Withholding Tax Threshold (ETB)",
    )
    top_buyers_limit_n = fields.Integer(
        related='company_id.top_buyers_limit_n',
        readonly=False,
        string="Default Top N Buyers Count",
    )
    top_buyers_default_metric = fields.Selection(
        related='company_id.top_buyers_default_metric',
        readonly=False,
        string="Default Ranking Metric",
    )
    top_buyers_default_period = fields.Selection(
        related='company_id.top_buyers_default_period',
        readonly=False,
        string="Default Analysis Period",
    )

