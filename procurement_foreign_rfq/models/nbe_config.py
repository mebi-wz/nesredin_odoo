from odoo import models, fields

class NBEConfig(models.Model):
    _name = 'nbe.config'
    _description = 'NBE Configuration'

    name = fields.Char(string='NBE Reference', required=True)
    active = fields.Boolean(default=True)
