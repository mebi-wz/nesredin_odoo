# -*- coding: utf-8 -*-
from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        check_company=True,
        help="Analytic Account / Cost Center tied to this warehouse for financial reporting and branch analytics.",
    )

    def _get_sequence_values(self, name=False, code=False):
        vals = super()._get_sequence_values(name=name, code=code)
        if 'int_type_id' in vals:
            vals['int_type_id']['prefix'] = 'STR/'
        return vals
