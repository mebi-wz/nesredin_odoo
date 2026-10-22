# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_return_order_id = fields.Many2one(
        'sale.order',
        string='Sales Return Order',
        copy=False,
        readonly=True,
        help="Sales Return Order that originated this credit note.",
    )
