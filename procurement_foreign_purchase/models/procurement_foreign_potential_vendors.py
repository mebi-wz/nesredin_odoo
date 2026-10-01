from odoo import models, fields

class PotentialVendors(models.Model):
    _name = 'potential.vendors'
    _description = 'Potential Vendors'

    name = fields.Char(string="Reference", default="New", readonly=True)

    requisition_line_id = fields.Many2one(
        'foreign.purchase.requisition.line',
        string="Requisition Line",
        required=True,
        ondelete='cascade'
    )

    line_ids = fields.One2many(
        'potential.vendors.line',
        'potential_id',
        string="Vendor Lines"
    )
class PotentialVendorsLine(models.Model):
    _name = 'potential.vendors.line'
    _description = 'Potential Vendors Line'
    potential_id = fields.Many2one(
        'potential.vendors',
        string="Potential",
        required=True,
        ondelete='cascade'
    )
    manufacturer = fields.Many2one(
        'res.partner',
        string="Manufacturer",
        domain=[('supplier_rank', '!=', 0)],
        required=True
    )

    foreign_is_sup_registered=fields.Boolean(string="Registered?")

    price = fields.Float(string="Unit Price")
    shelf_life_in_month= fields.Float(string="Shelf life in months")
