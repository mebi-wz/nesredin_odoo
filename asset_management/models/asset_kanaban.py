from odoo import tools, models, fields, api


class AssetKanban(models.Model):
    _name = "am.asset.kanban"
    _description = "Assets Kanban View"
    _auto = False

    asset_id = fields.Many2one('am.asset', string="Asset")
    name = fields.Char(string="Asset Name")
    location = fields.Char(string="Location")
    status_id = fields.Many2one('am.asset.status', string="Status")
    employee_id = fields.Many2one('hr.employee', string="Employee")
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse")
    tag_number = fields.Char(string="Tag Number")
    qr_code_number = fields.Char(string="Tag Number")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW am_asset_kanban AS (
                SELECT
                    row_number() over() as id,
                    ea.asset_id as asset_id,
                    a.name as name,
                    e.name as location,
                    a.status_id as status_id,
                    ea.employee_id as employee_id,
                    NULL as warehouse_id,
                    a.tag_number as tag_number,
                    a.tag_number as qr_code_number
                FROM am_employee_asset ea
                JOIN am_asset a ON ea.asset_id = a.id
                JOIN hr_employee e ON ea.employee_id = e.id

                UNION ALL

                SELECT
                    row_number() over() + 100000 as id,
                    ws.asset_id as asset_id,
                    a.name as name,
                    w.name as location,
                    a.status_id as status_id,
                    NULL as employee_id,
                    ws.warehouse_id as warehouse_id,
                    a.tag_number as tag_number,
                    a.tag_number as qr_code_number
                FROM am_asset_warehouse_stock ws
                JOIN am_asset a ON ws.asset_id = a.id
                JOIN stock_warehouse w ON ws.warehouse_id = w.id
            )
        """)
