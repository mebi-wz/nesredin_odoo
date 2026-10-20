# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    part_number = fields.Char(
        string='Part Number',
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
        res['part_number'] = 't.part_number'
        res['write_date'] = 'MAX(l.write_date)'
        return res

    def _group_by_sale(self):
        return super()._group_by_sale() + ", t.part_number"
