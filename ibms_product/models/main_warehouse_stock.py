# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _


class MainWarehouseStock(models.Model):
    _name = 'main.warehouse.stock'
    _description = 'Main Warehouse Stock (View Only)'
    _auto = False
    _log_access = True
    _order = 'default_code, product_id, location_id'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        readonly=True,
    )
    image_128 = fields.Image(
        related='product_id.image_128',
        string='Image',
        readonly=True,
    )
    default_code = fields.Char(
        string='Product Code',
        readonly=True,
    )
    part_number = fields.Char(
        string='Primary Part #',
        readonly=True,
    )
    secondary_parts_display = fields.Char(
        string='Secondary Part Numbers',
        readonly=True,
        help="Cross-reference and alternative OEM part numbers.",
    )
    categ_id = fields.Many2one(
        'product.category',
        string='Category',
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        readonly=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Location / Rack',
        readonly=True,
    )
    quantity = fields.Float(
        string='On Hand Quantity',
        readonly=True,
    )
    reserved_quantity = fields.Float(
        string='Reserved Quantity',
        readonly=True,
    )
    available_quantity = fields.Float(
        string='Available to Use',
        readonly=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        readonly=True,
    )

    def action_view_product(self):
        self.ensure_one()
        return {
            'name': self.product_id.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW main_warehouse_stock AS (
                SELECT
                    pp.id AS id,
                    pp.id AS product_id,
                    pp.product_tmpl_id AS product_tmpl_id,
                    pp.default_code AS default_code,
                    pt.part_number AS part_number,
                    pt.secondary_parts_display AS secondary_parts_display,
                    pt.categ_id AS categ_id,
                    sw.id AS warehouse_id,
                    COALESCE(MAX(sq.location_id), sw.lot_stock_id) AS location_id,
                    COALESCE(SUM(sq.quantity), 0.0) AS quantity,
                    COALESCE(SUM(sq.reserved_quantity), 0.0) AS reserved_quantity,
                    COALESCE(SUM(sq.quantity - sq.reserved_quantity), 0.0) AS available_quantity,
                    pt.uom_id AS uom_id,
                    COALESCE(pt.company_id, sw.company_id) AS company_id,
                    pt.create_uid AS create_uid,
                    pt.create_date AS create_date,
                    pt.write_uid AS write_uid,
                    pt.write_date AS write_date
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                CROSS JOIN (
                    SELECT id, lot_stock_id, company_id 
                    FROM stock_warehouse 
                    WHERE is_main_warehouse = TRUE OR code = 'WH' 
                    ORDER BY is_main_warehouse DESC, id ASC 
                    LIMIT 1
                ) sw
                LEFT JOIN stock_location sl ON (sl.warehouse_id = sw.id AND sl.usage = 'internal')
                LEFT JOIN stock_quant sq ON (sq.product_id = pp.id AND sq.location_id = sl.id)
                WHERE pt.active = TRUE AND pp.active = TRUE
                GROUP BY 
                    pp.id, pp.product_tmpl_id, pp.default_code, 
                    pt.part_number, pt.secondary_parts_display, pt.categ_id, 
                    sw.id, sw.lot_stock_id, pt.uom_id, pt.company_id, sw.company_id, 
                    pt.create_uid, pt.create_date, pt.write_uid, pt.write_date
            )
        """)

