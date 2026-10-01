# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'res_users_stock_warehouse_rel',
        'user_id',
        'warehouse_id',
        string='Allowed Warehouses',
        help="Warehouses this user is authorized to access and view transfers for. If empty, the user has access to all warehouses.",
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse',
        help="Primary branch or warehouse for this user.",
    )
