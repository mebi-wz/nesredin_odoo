# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockLocationTransfer(models.Model):
    _name = 'stock.location.transfer'
    _description = 'Location Stock Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Transfer #',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', copy=False, tracking=True)

    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        readonly=True,
        copy=False
    )

    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        tracking=True
    )

    # -------------------------------------------------------------
    # Source (From)
    # -------------------------------------------------------------
    source_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Source Analytic Account',
        required=True,
        check_company=True,
        tracking=True,
        help="Cost Center of the source warehouse/branch."
    )
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        required=True,
        check_company=True,
        tracking=True,
        help="Warehouse where products will be transferred from."
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        compute='_compute_locations',
        store=True,
        readonly=True
    )

    # -------------------------------------------------------------
    # Destination (To)
    # -------------------------------------------------------------
    dest_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Destination Analytic Account',
        required=True,
        check_company=True,
        tracking=True,
        help="Cost Center / Profit Center of the destination shop/branch."
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        required=True,
        check_company=True,
        tracking=True,
        help="Warehouse/Shop where products will be transferred to."
    )
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        compute='_compute_locations',
        store=True,
        readonly=True
    )

    line_ids = fields.One2many(
        'stock.location.transfer.line',
        'transfer_id',
        string='Products to Transfer',
        copy=True
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Transfer (Picking)',
        readonly=True,
        copy=False
    )

    note = fields.Text(string='Notes')

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # -------------------------------------------------------------
    # Computes & Onchanges
    # -------------------------------------------------------------
    @api.depends('source_warehouse_id', 'dest_warehouse_id')
    def _compute_locations(self):
        for rec in self:
            rec.location_id = rec.source_warehouse_id.lot_stock_id.id if rec.source_warehouse_id else False
            rec.location_dest_id = rec.dest_warehouse_id.lot_stock_id.id if rec.dest_warehouse_id else False

    @api.onchange('source_analytic_account_id')
    def _onchange_source_analytic_account_id(self):
        if self.source_analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.source_analytic_account_id.id),
                ('company_id', '=', self.company_id.id)
            ])
            if self.source_warehouse_id and self.source_warehouse_id not in warehouses:
                self.source_warehouse_id = False

            if len(warehouses) == 1:
                self.source_warehouse_id = warehouses[0].id
            elif not warehouses:
                self.source_warehouse_id = False
        else:
            self.source_warehouse_id = False

    @api.onchange('dest_analytic_account_id')
    def _onchange_dest_analytic_account_id(self):
        if self.dest_analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.dest_analytic_account_id.id),
                ('company_id', '=', self.company_id.id)
            ])
            if self.dest_warehouse_id and self.dest_warehouse_id not in warehouses:
                self.dest_warehouse_id = False

            if len(warehouses) == 1:
                self.dest_warehouse_id = warehouses[0].id
            elif not warehouses:
                self.dest_warehouse_id = False
        else:
            self.dest_warehouse_id = False

    # -------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.location.transfer') or _('New')
        return super().create(vals_list)

    # -------------------------------------------------------------
    # Workflow Actions
    # -------------------------------------------------------------
    def action_submit(self):
        for transfer in self:
            if not transfer.line_ids:
                raise ValidationError(_("Please add at least one product before submitting the transfer!"))
            if transfer.source_warehouse_id == transfer.dest_warehouse_id:
                raise ValidationError(_("Source Warehouse and Destination Warehouse cannot be the same!"))
            transfer.state = 'submitted'

    def action_approve(self):
        Picking = self.env['stock.picking']
        for transfer in self:
            if not transfer.line_ids:
                raise ValidationError(_("No products specified to transfer!"))

            # Determine picking type (Internal transfer of source warehouse)
            picking_type = transfer.source_warehouse_id.int_type_id
            if not picking_type:
                picking_type = self.env['stock.picking.type'].search([
                    ('code', '=', 'internal'),
                    ('warehouse_id', '=', transfer.source_warehouse_id.id)
                ], limit=1)
            if not picking_type:
                picking_type = self.env['stock.picking.type'].search([
                    ('code', '=', 'internal'),
                    ('company_id', '=', transfer.company_id.id)
                ], limit=1)

            if not picking_type:
                raise ValidationError(_("No internal transfer operation type found for warehouse %s.") % transfer.source_warehouse_id.name)

            # Create physical stock.picking
            picking_vals = {
                'picking_type_id': picking_type.id,
                'location_id': transfer.location_id.id,
                'location_dest_id': transfer.location_dest_id.id,
                'origin': transfer.name,
                'company_id': transfer.company_id.id,
                'move_ids': [
                    (0, 0, {
                        'description_picking': line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'product_uom': line.product_uom_id.id,
                        'location_id': transfer.location_id.id,
                        'location_dest_id': transfer.location_dest_id.id,
                        'company_id': transfer.company_id.id,
                    }) for line in transfer.line_ids
                ]
            }
            picking = Picking.create(picking_vals)
            picking.action_confirm()
            picking.action_assign()

            # Set quantity done, mark picked, and validate
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()

            transfer.picking_id = picking.id
            transfer.state = 'approved'

    def action_cancel(self):
        for transfer in self:
            if transfer.picking_id and transfer.picking_id.state not in ('done', 'cancel'):
                transfer.picking_id.action_cancel()
            transfer.state = 'cancel'

    def action_view_picking(self):
        self.ensure_one()
        return {
            'name': _('Stock Transfer'),
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'type': 'ir.actions.act_window',
        }


class StockLocationTransferLine(models.Model):
    _name = 'stock.location.transfer.line'
    _description = 'Location Stock Transfer Line'

    transfer_id = fields.Many2one(
        'stock.location.transfer',
        string='Transfer Reference',
        required=True,
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('type', '=', 'consu')]"
    )

    description = fields.Char(
        string='Description',
        related='product_id.name',
        readonly=True
    )

    product_uom_qty = fields.Float(
        string='Demand Quantity',
        default=1.0,
        required=True
    )

    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True
    )
