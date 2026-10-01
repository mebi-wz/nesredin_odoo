# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
        readonly=False,
        help="Employee or branch user who requested this stock transfer."
    )

    source_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Source Analytic Account',
        check_company=True,
        help="Cost Center of the source warehouse/branch."
    )
    dest_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Destination Analytic Account',
        check_company=True,
        help="Cost Center / Profit Center of the destination shop/branch."
    )

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        check_company=True,
        help="Warehouse where products will be picked from."
    )
    dest_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        check_company=True,
        help="Warehouse/Shop where products will be transferred to."
    )

    transfer_state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('cancel', 'Cancelled'),
    ], string='Transfer Status', default='draft', copy=False, tracking=True)

    # -------------------------------------------------------------
    # Onchanges for Source
    # -------------------------------------------------------------
    @api.onchange('source_analytic_account_id')
    def _onchange_source_analytic_account_id(self):
        if self.source_analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.source_analytic_account_id.id),
                ('company_id', '=', self.company_id.id or self.env.company.id)
            ])
            # If current warehouse doesn't match the new analytic account, clear it
            if self.source_warehouse_id and self.source_warehouse_id not in warehouses:
                self.source_warehouse_id = False
                self.location_id = False

            # If exactly one warehouse is linked to this analytic account, auto-select it
            if len(warehouses) == 1:
                self.source_warehouse_id = warehouses[0].id
                if warehouses[0].lot_stock_id:
                    self.location_id = warehouses[0].lot_stock_id.id
            elif not warehouses:
                self.source_warehouse_id = False
                self.location_id = False
        else:
            self.source_warehouse_id = False
            self.location_id = False

    @api.onchange('source_warehouse_id')
    def _onchange_source_warehouse_id(self):
        if self.source_warehouse_id:
            if self.source_warehouse_id.lot_stock_id:
                self.location_id = self.source_warehouse_id.lot_stock_id.id
            if self.source_warehouse_id.analytic_account_id and not self.source_analytic_account_id:
                self.source_analytic_account_id = self.source_warehouse_id.analytic_account_id.id

    # -------------------------------------------------------------
    # Onchanges for Destination
    # -------------------------------------------------------------
    @api.onchange('dest_analytic_account_id')
    def _onchange_dest_analytic_account_id(self):
        if self.dest_analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.dest_analytic_account_id.id),
                ('company_id', '=', self.company_id.id or self.env.company.id)
            ])
            # If current warehouse doesn't match the new analytic account, clear it
            if self.dest_warehouse_id and self.dest_warehouse_id not in warehouses:
                self.dest_warehouse_id = False
                self.location_dest_id = False

            # If exactly one warehouse is linked to this analytic account, auto-select it
            if len(warehouses) == 1:
                self.dest_warehouse_id = warehouses[0].id
                if warehouses[0].lot_stock_id:
                    self.location_dest_id = warehouses[0].lot_stock_id.id
            elif not warehouses:
                self.dest_warehouse_id = False
                self.location_dest_id = False
        else:
            self.dest_warehouse_id = False
            self.location_dest_id = False

    @api.onchange('dest_warehouse_id')
    def _onchange_dest_warehouse_id(self):
        if self.dest_warehouse_id:
            if self.dest_warehouse_id.lot_stock_id:
                self.location_dest_id = self.dest_warehouse_id.lot_stock_id.id
            if self.dest_warehouse_id.analytic_account_id and not self.dest_analytic_account_id:
                self.dest_analytic_account_id = self.dest_warehouse_id.analytic_account_id.id

    # -------------------------------------------------------------
    # Default Get
    # -------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('default_is_location_transfer') or self.env.context.get('default_picking_type_code') == 'internal':
            company = self.env.company
            internal_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('company_id', '=', company.id)
            ], limit=1)
            if internal_type:
                res['picking_type_id'] = internal_type.id
                if not res.get('location_id') and internal_type.default_location_src_id:
                    res['location_id'] = internal_type.default_location_src_id.id
                if not res.get('location_dest_id') and internal_type.default_location_dest_id:
                    res['location_dest_id'] = internal_type.default_location_dest_id.id

            default_wh = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
            if default_wh:
                if default_wh.analytic_account_id:
                    res['source_analytic_account_id'] = default_wh.analytic_account_id.id
                res['source_warehouse_id'] = default_wh.id
                if default_wh.lot_stock_id:
                    res['location_id'] = default_wh.lot_stock_id.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            picking_type_id = vals.get('picking_type_id')
            if picking_type_id:
                picking_type = self.env['stock.picking.type'].browse(picking_type_id)
                if picking_type.code == 'internal' and picking_type.sequence_id:
                    prefix = picking_type.sequence_id.prefix or ''
                    if 'STOR' in prefix or 'INT' in prefix or prefix.startswith('WH/'):
                        picking_type.sequence_id.sudo().write({'prefix': 'STR/'})
        return super().create(vals_list)

    # -------------------------------------------------------------
    # Status Workflow Actions: Draft -> Submitted -> Approved
    # -------------------------------------------------------------
    def action_transfer_submit(self):
        for picking in self:
            if not picking.move_ids:
                raise ValidationError(_("Please add at least one product before submitting the transfer!"))
            if not picking.location_id or not picking.location_dest_id:
                raise ValidationError(_("Source and Destination locations must be set from the selected warehouses!"))
            if picking.state == 'draft':
                picking.action_confirm()
            picking.transfer_state = 'submitted'

    def action_transfer_approve(self):
        for picking in self:
            for move in picking.move_ids:
                if not move.quantity and move.product_uom_qty:
                    move.quantity = move.product_uom_qty
            res = picking.button_validate()
            if picking.state == 'done':
                picking.transfer_state = 'approved'
            elif isinstance(res, dict):
                return res
            else:
                picking.transfer_state = 'approved'
            return res

    def action_transfer_cancel(self):
        for picking in self:
            picking.action_cancel()
            picking.transfer_state = 'cancel'
