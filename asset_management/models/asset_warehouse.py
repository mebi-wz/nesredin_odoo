from odoo import models, fields, api


class AssetWarehouse(models.Model):
    _name = 'am.asset.warehouse'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Asset Warehouse'

    name = fields.Char(string="Warehouse Name", required=True, tracking=True)
    branch_id = fields.Many2one('account.analytic.account', string="Branch", required=True, tracking=True)
    code = fields.Char(string="Warehouse Code", tracking=True)
    note = fields.Text(string="Description", tracking=True)
    location_ids = fields.One2many('am.asset.location', 'warehouse_id', string="Locations")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True, tracking=True)

    stock_count = fields.Integer(string="Assets Count", compute="_compute_stock_count")

    def _compute_stock_count(self):
        for warehouse in self:
            warehouse.stock_count = self.env['am.asset.warehouse.stock'].search_count([('warehouse_id', '=', warehouse.id)])

    def action_view_stock(self):
        self.ensure_one()
        return {
            'name': f'Assets in {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'am.asset.warehouse.stock',
            'view_mode': 'list,kanban,form',
            'domain': [('warehouse_id', '=', self.id)],
            'context': {'default_warehouse_id': self.id},
        }

class AssetLocation(models.Model):
    _name = 'am.asset.location'
    _description = 'Warehouse Location'

    name = fields.Char(string="Location Name", required=True)
    warehouse_id = fields.Many2one('am.asset.warehouse', string="Warehouse", required=True, ondelete='cascade')
    code = fields.Char(string="Location Code")
    note = fields.Text(string="Description")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)