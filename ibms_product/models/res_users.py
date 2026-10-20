# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'res_users_stock_warehouse_rel',
        'user_id',
        'warehouse_id',
        string='Allowed Warehouses',
        help="Warehouses this user is authorized to access and view operations for. If empty and Primary Branch is also empty, the user has access to all warehouses.",
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Primary Branch Warehouse',
        help="Primary branch or warehouse for this user. When assigned, this warehouse is automatically authorized.",
    )

    @api.onchange('default_warehouse_id')
    def _onchange_default_warehouse_id(self):
        if self.default_warehouse_id and self.default_warehouse_id not in self.allowed_warehouse_ids:
            self.allowed_warehouse_ids = [(4, self.default_warehouse_id.id)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            default_wh = vals.get('default_warehouse_id')
            if default_wh:
                allowed_cmds = vals.get('allowed_warehouse_ids') or []
                # Check if default_wh is already linked
                wh_ids = set()
                for cmd in allowed_cmds:
                    if len(cmd) == 3 and cmd[0] in (4,):
                        wh_ids.add(cmd[1])
                    elif len(cmd) == 3 and cmd[0] == 6:
                        wh_ids.update(cmd[2])
                if default_wh not in wh_ids:
                    allowed_cmds.append((4, default_wh))
                vals['allowed_warehouse_ids'] = allowed_cmds
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'default_warehouse_id' in vals and vals.get('default_warehouse_id'):
            for user in self:
                if user.default_warehouse_id and user.default_warehouse_id not in user.allowed_warehouse_ids:
                    user.allowed_warehouse_ids = [(4, user.default_warehouse_id.id)]
        return res

    def get_accessible_warehouse_ids(self):
        """Returns list of warehouse IDs accessible by this user."""
        return (self.allowed_warehouse_ids | self.default_warehouse_id).ids
