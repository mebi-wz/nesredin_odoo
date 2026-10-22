# -*- coding: utf-8 -*-
from odoo import fields, models, _


class SaleReport(models.Model):
    _inherit = 'sale.report'

    default_code = fields.Char(
        string='Product Code',
        readonly=True,
    )
    part_number = fields.Char(
        string='Part Number',
        readonly=True,
    )
    secondary_parts_display = fields.Char(
        string='Secondary Part Numbers',
        readonly=True,
    )
    has_secondary_parts = fields.Boolean(
        string='Has Secondary Parts',
        readonly=True,
    )
    secondary_parts_count = fields.Integer(
        string='Secondary Parts Count',
        readonly=True,
    )
    write_date = fields.Datetime(
        string='Write Date',
        readonly=True,
    )
    image_128 = fields.Binary(
        string='Image',
        related='product_id.image_128',
        readonly=True,
    )
    image_1920 = fields.Binary(
        string='Full Image',
        related='product_id.image_1920',
        readonly=True,
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['default_code'] = 'p.default_code'
        res['part_number'] = 't.part_number'
        res['secondary_parts_display'] = 't.secondary_parts_display'
        res['has_secondary_parts'] = 't.has_secondary_parts'
        res['secondary_parts_count'] = 't.secondary_parts_count'
        res['write_date'] = 'MAX(l.write_date)'
        return res

    def _group_by_sale(self):
        return super()._group_by_sale() + ", p.default_code, t.part_number, t.secondary_parts_display, t.has_secondary_parts, t.secondary_parts_count"

    def action_view_secondary_part_numbers(self):
        """Opens popup dialog listing all secondary/cross-reference part numbers for this product."""
        self.ensure_one()
        product = self.product_tmpl_id or (self.product_id and self.product_id.product_tmpl_id)
        if product:
            return product.action_view_secondary_part_numbers()
        return False
