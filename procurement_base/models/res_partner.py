from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    vendor_type = fields.Selection([
        ('local', 'Local'),
        ('foreign', 'Foreign')
    ], string='Vendor Type', tracking=True)
