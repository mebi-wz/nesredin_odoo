# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def write(self, vals):
        """Record the user who actually enters the physical count.

        Odoo assigns a counter when a count is requested or a new inventory
        line is created, but editing the counted quantity on an existing quant
        does not update ``user_id``.  Physical Inventory writes carry the
        ``inventory_mode`` context, so keep the behaviour scoped to that flow.
        """
        if (
            self._is_inventory_mode()
            and {'inventory_quantity', 'inventory_quantity_auto_apply'} & vals.keys()
        ):
            vals = {**vals, 'user_id': self.env.user.id}
        return super().write(vals)

    part_number = fields.Char(
        string='Part Number',
        related='product_id.part_number',
        readonly=True,
    )
    image_128 = fields.Image(
        string='Image',
        related='product_id.image_128',
        readonly=True,
    )
    image_1920 = fields.Image(
        string='Full Image',
        related='product_id.image_1920',
        readonly=True,
    )
