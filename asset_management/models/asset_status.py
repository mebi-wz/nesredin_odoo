from odoo import models, fields

class AssetStatus(models.Model):
    _name = 'am.asset.status'
    _description = 'Asset Status'

    name = fields.Char(string='Status Name', required=True)
    code = fields.Char(string='Code', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)