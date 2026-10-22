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

    @api.model
    def _get_invalidation_fields(self):
        """Include warehouse fields so Odoo's registry cache invalidates on changes."""
        res = super()._get_invalidation_fields()
        return res | {'allowed_warehouse_ids', 'default_warehouse_id'}

    @api.onchange('default_warehouse_id')
    def _onchange_default_warehouse_id(self):
        # Retrieve previous default warehouse if editing an existing user
        old_wh = self._origin.default_warehouse_id if hasattr(self, '_origin') else False
        new_wh = self.default_warehouse_id

        # If changing from an old warehouse, replace the old warehouse in allowed_warehouse_ids
        if old_wh and old_wh != new_wh and old_wh in self.allowed_warehouse_ids:
            self.allowed_warehouse_ids = self.allowed_warehouse_ids - old_wh

        if new_wh and new_wh not in self.allowed_warehouse_ids:
            self.allowed_warehouse_ids = self.allowed_warehouse_ids | new_wh

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            default_wh = vals.get('default_warehouse_id')
            if default_wh:
                allowed_cmds = vals.get('allowed_warehouse_ids') or []
                wh_ids = set()
                for cmd in allowed_cmds:
                    if len(cmd) == 3 and cmd[0] in (4,):
                        wh_ids.add(cmd[1])
                    elif len(cmd) == 3 and cmd[0] == 6:
                        wh_ids.update(cmd[2])
                if default_wh not in wh_ids:
                    allowed_cmds.append((4, default_wh))
                vals['allowed_warehouse_ids'] = allowed_cmds
        users = super().create(vals_list)
        self.env.registry.clear_cache()
        return users

    def write(self, vals):
        # Track old default warehouses before writing so we can remove them if needed
        old_defaults = {}
        if 'default_warehouse_id' in vals:
            old_defaults = {user.id: user.default_warehouse_id.id for user in self if user.default_warehouse_id}

        res = super().write(vals)

        # 1. If default_warehouse_id was updated, ensure old default is removed and new default is added
        if 'default_warehouse_id' in vals:
            new_wh_id = vals.get('default_warehouse_id')
            for user in self:
                old_wh_id = old_defaults.get(user.id)
                # If old warehouse changed and allowed_warehouse_ids wasn't explicitly provided, replace old with new
                if old_wh_id and old_wh_id != new_wh_id and 'allowed_warehouse_ids' not in vals:
                    if old_wh_id in user.allowed_warehouse_ids.ids:
                        user.allowed_warehouse_ids = [(3, old_wh_id)]
                if new_wh_id and new_wh_id not in user.allowed_warehouse_ids.ids:
                    user.allowed_warehouse_ids = [(4, new_wh_id)]

        # 2. If allowed_warehouse_ids was updated directly without default_warehouse_id:
        # Sync default_warehouse_id so it doesn't hold an obsolete warehouse
        if 'allowed_warehouse_ids' in vals and 'default_warehouse_id' not in vals:
            for user in self:
                if user.default_warehouse_id and user.default_warehouse_id not in user.allowed_warehouse_ids:
                    user.default_warehouse_id = user.allowed_warehouse_ids[:1].id or False

        # 3. Always clear Odoo's registry and record rule cache immediately
        if 'default_warehouse_id' in vals or 'allowed_warehouse_ids' in vals:
            self.env.registry.clear_cache()

        return res

    def get_accessible_warehouse_ids(self):
        """Returns list of warehouse IDs accessible by this user."""
        return (self.allowed_warehouse_ids | self.default_warehouse_id).ids
