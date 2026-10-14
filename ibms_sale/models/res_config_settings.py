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
