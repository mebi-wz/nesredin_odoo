from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    vendor_type = fields.Selection([
        ('local', 'Local'),
        ('foreign', 'Foreign')
    ], string='Vendor Type', tracking=True)

    @api.onchange('vendor_type')
    def _onchange_vendor_type_customer_type(self):
        if self.vendor_type and hasattr(self, 'customer_type'):
            self.customer_type = False
        elif not self.vendor_type and hasattr(self, 'customer_type') and not self.customer_type:
            self.customer_type = 'retailer'
