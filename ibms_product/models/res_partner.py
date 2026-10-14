# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_type = fields.Selection([
        ('retailer', 'Retailer'),
        ('wholesaler', 'Wholesaler'),
    ], string='Customer Type', default='retailer', required=True, tracking=True,
       help="Categorizes customer as Retailer or Wholesaler to automatically determine product selling price.")
