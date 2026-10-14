# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_type = fields.Selection([
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
    ], string='Customer Type',
       default=lambda self: False if self.env.context.get('default_vendor_type') or self.env.context.get('default_supplier_rank') else 'retailer',
       tracking=True,
       help="Categorizes customer as Retailer or Wholesaler to automatically determine product selling price.")
