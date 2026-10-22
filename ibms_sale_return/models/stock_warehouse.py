# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    sale_return_type_id = fields.Many2one(
        'stock.picking.type',
        string='Returned from Sales Type',
        check_company=True,
        copy=False,
        help="Dedicated operation type for customer sales returns (Receipt).",
    )

    def _get_or_create_sale_return_type(self):
        """Finds or creates a dedicated 'Returned from Sales' operation type (Receipt) for this warehouse."""
        self.ensure_one()
        if self.sale_return_type_id and self.sale_return_type_id.active:
            return self.sale_return_type_id

        PickingType = self.env['stock.picking.type']
        picking_type = PickingType.search([
            ('warehouse_id', '=', self.id),
            ('code', '=', 'incoming'),
            ('sequence_code', '=', 'RET'),
        ], limit=1)

        if not picking_type:
            picking_type = PickingType.search([
                ('warehouse_id', '=', self.id),
                ('code', '=', 'incoming'),
                ('name', '=', _('Returned from Sales')),
            ], limit=1)

        if not picking_type:
            customer_loc = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
            if not customer_loc:
                customer_loc = self.env['stock.location'].search([('usage', '=', 'customer')], limit=1)

            dest_loc = self.lot_stock_id

            max_seq = PickingType.search_read(
                [('sequence', '!=', False)], ['sequence'], limit=1, order='sequence desc'
            )
            sequence = (max_seq[0]['sequence'] if max_seq else 0) + 1

            vals = {
                'name': _('Returned from Sales'),
                'code': 'incoming',
                'sequence_code': 'RET',
                'warehouse_id': self.id,
                'company_id': self.company_id.id,
                'default_location_src_id': customer_loc.id if customer_loc else False,
                'default_location_dest_id': dest_loc.id if dest_loc else False,
                'sequence': sequence,
                'color': self.in_type_id.color if self.in_type_id else 0,
                'return_picking_type_id': self.out_type_id.id if self.out_type_id else False,
            }
            picking_type = PickingType.create(vals)

        # Ensure return_picking_type_id on warehouse delivery order points to this return type
        if self.out_type_id and self.out_type_id.return_picking_type_id != picking_type:
            self.out_type_id.write({'return_picking_type_id': picking_type.id})

        if self.sale_return_type_id != picking_type:
            self.write({'sale_return_type_id': picking_type.id})

        return picking_type

    def _create_or_update_sequences_and_picking_types(self):
        res = super()._create_or_update_sequences_and_picking_types()
        for warehouse in self:
            warehouse._get_or_create_sale_return_type()
        return res

    @api.model
    def create_missing_sale_return_picking_types(self):
        """Initializes 'Returned from Sales' operation type for all warehouses in system."""
        warehouses = self.search([])
        for warehouse in warehouses:
            ret_type = warehouse._get_or_create_sale_return_type()
            # Also migrate existing return pickings to the dedicated return picking type
            old_pickings = self.env['stock.picking'].search([
                ('picking_type_id', '=', warehouse.in_type_id.id),
                ('sale_id.is_return', '=', True),
            ])
            if old_pickings:
                old_pickings.write({'picking_type_id': ret_type.id})
                old_pickings.move_ids.write({'picking_type_id': ret_type.id})
