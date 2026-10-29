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
        ('in_transit', 'In Transit'),
        ('received', 'Received'),
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

    sent_by_id = fields.Many2one(
        'res.users',
        string='Sent By',
        readonly=True,
        copy=False,
        tracking=True
    )

    sent_date = fields.Datetime(
        string='Sent On',
        readonly=True,
        copy=False
    )

    received_by_id = fields.Many2one(
        'res.users',
        string='Received By',
        readonly=True,
        copy=False,
        tracking=True
    )

    received_date = fields.Datetime(
        string='Received On',
        readonly=True,
        copy=False
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

    issue_picking_id = fields.Many2one(
        'stock.picking',
        string='Issue Picking (WH1)',
        readonly=True,
        copy=False
    )

    receive_picking_id = fields.Many2one(
        'stock.picking',
        string='Receive Picking (WH2)',
        readonly=True,
        copy=False
    )

    picking_id = fields.Many2one(
        'stock.picking',
        string='Primary Stock Move',
        readonly=True,
        copy=False
    )

    picking_ids = fields.Many2many(
        'stock.picking',
        compute='_compute_picking_ids',
        string='Pickings',
        compute_sudo=True
    )

    picking_count = fields.Integer(
        compute='_compute_picking_ids',
        string='Pickings Count',
        compute_sudo=True
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

    @api.depends('issue_picking_id', 'receive_picking_id', 'picking_id')
    def _compute_picking_ids(self):
        for rec in self:
            rec_sudo = rec.sudo()
            pickings = rec_sudo.issue_picking_id | rec_sudo.receive_picking_id | rec_sudo.picking_id
            rec.picking_ids = pickings
            rec.picking_count = len(pickings)

    def _get_transit_location(self):
        self.ensure_one()
        transit = self.env['stock.location'].sudo().search([
            ('usage', '=', 'transit'),
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_id', '=', False),
        ], limit=1)
        if not transit:
            transit = self.env.ref('stock.stock_location_inter_wh', raise_if_not_found=False)
        if not transit:
            transit = self.env['stock.location'].sudo().search([('usage', '=', 'transit')], limit=1)
        if not transit:
            raise ValidationError(
                _("No transit location found (usage='transit'). Please configure an Inter-Warehouse Transit location in Inventory > Configuration > Locations.")
            )
        return transit

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
        """
        STEP 1 — Manager approves the request.
        Creates TWO stock.picking records:
        1. Issue Picking (Source Warehouse): WH1/Stock -> Transit Location (state: Ready)
        2. Receive Picking (Destination Warehouse): Transit Location -> WH2/Stock (state: Waiting)
        """
        Picking = self.env['stock.picking'].sudo()
        for transfer in self:
            if not transfer.line_ids:
                raise ValidationError(_("No products specified to transfer!"))

            transit_loc = transfer._get_transit_location()

            # 1. Source Warehouse Picking Type (Issue / Internal Transfer)
            source_wh = transfer.source_warehouse_id
            source_picking_type = source_wh.int_type_id or self.env['stock.picking.type'].sudo().search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', source_wh.id),
            ], limit=1) or self.env['stock.picking.type'].sudo().search([
                ('code', '=', 'internal'),
                ('company_id', '=', transfer.company_id.id),
            ], limit=1)

            if not source_picking_type:
                raise ValidationError(
                    _("No internal transfer operation type found for source warehouse %s.") % source_wh.name
                )

            # 2. Create Issue Picking for Warehouse 1 (Source -> Transit)
            issue_vals = {
                'picking_type_id': source_picking_type.id,
                'location_id': transfer.location_id.id,
                'location_dest_id': transit_loc.id,
                'origin': f"{transfer.name} (Issue)",
                'location_transfer_id': transfer.id,
                'transfer_operation_type': 'issue',
                'company_id': transfer.company_id.id,
                'move_ids': [
                    (0, 0, {
                        'description_picking': line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'product_uom': line.product_uom_id.id,
                        'location_id': transfer.location_id.id,
                        'location_dest_id': transit_loc.id,
                        'company_id': transfer.company_id.id,
                    }) for line in transfer.line_ids
                ]
            }
            issue_picking = Picking.create(issue_vals)
            issue_picking.action_confirm()
            issue_picking.action_assign()

            transfer.sudo().write({
                'issue_picking_id': issue_picking.id,
                'picking_id': issue_picking.id,
                'state': 'approved',
            })
            transfer.message_post(
                body=_("Transfer approved. Created Issue Picking <b>%s</b> for %s.") % (
                    issue_picking.name,
                    source_wh.name,
                )
            )

    def _create_receive_picking(self):
        """
        Creates the Receive Picking for Destination Warehouse (Warehouse 2).
        Called sequentially when items are physically dispatched (action_send).
        This ensures Warehouse 2's dashboard only shows the incoming transfer once items are in transit.
        """
        Picking = self.env['stock.picking'].sudo()
        for transfer in self:
            if transfer.receive_picking_id:
                continue

            transit_loc = transfer._get_transit_location()
            dest_wh = transfer.dest_warehouse_id
            dest_picking_type = dest_wh.int_type_id or self.env['stock.picking.type'].sudo().search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', dest_wh.id),
            ], limit=1) or self.env['stock.picking.type'].sudo().search([
                ('code', '=', 'internal'),
                ('company_id', '=', transfer.company_id.id),
            ], limit=1)

            if not dest_picking_type:
                raise ValidationError(
                    _("No internal transfer operation type found for destination warehouse %s.") % dest_wh.name
                )

            receive_vals = {
                'picking_type_id': dest_picking_type.id,
                'location_id': transit_loc.id,
                'location_dest_id': transfer.location_dest_id.id,
                'origin': f"{transfer.name} (Receive)",
                'location_transfer_id': transfer.id,
                'transfer_operation_type': 'receive',
                'company_id': transfer.company_id.id,
                'move_ids': [
                    (0, 0, {
                        'description_picking': line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'product_uom': line.product_uom_id.id,
                        'location_id': transit_loc.id,
                        'location_dest_id': transfer.location_dest_id.id,
                        'company_id': transfer.company_id.id,
                    }) for line in transfer.line_ids
                ]
            }
            receive_picking = Picking.create(receive_vals)
            receive_picking.action_confirm()
            receive_picking.action_assign()

            transfer.sudo().write({
                'receive_picking_id': receive_picking.id,
            })

    def action_send(self):
        """
        STEP 2 — Source warehouse staff confirms items have been physically dispatched.
        Only users belonging to the source warehouse (via allowed_warehouse_ids) can do this.
        Validates the Issue Picking: Source/Stock -> Transit Location.
        Then creates the Receive Picking on Warehouse 2's dashboard (one after the other).
        """
        for transfer in self:
            user = self.env.user
            allowed_whs = user.allowed_warehouse_ids
            if allowed_whs and transfer.source_warehouse_id not in allowed_whs:
                raise ValidationError(
                    _("Only staff from '%s' can mark this transfer as sent.") % transfer.source_warehouse_id.name
                )

            issue_picking = transfer.issue_picking_id or transfer.picking_id
            if not issue_picking:
                raise ValidationError(_("No issue picking found for this transfer."))

            issue_sudo = issue_picking.sudo()
            if issue_sudo.state not in ('done', 'cancel'):
                for move in issue_sudo.move_ids:
                    if move.state not in ('done', 'cancel'):
                        move.quantity = move.product_uom_qty
                        move.picked = True
                issue_sudo.button_validate()

            # Now create Receive Picking for Destination Warehouse (shows on WH2 dashboard)
            transfer._create_receive_picking()

            transfer.sudo().write({
                'state': 'in_transit',
                'sent_by_id': user.id,
                'sent_date': fields.Datetime.now(),
            })
            transfer.message_post(
                body=_("📦 Items dispatched from <b>%s</b> by %s. Issue picking <b>%s</b> validated. Created Receive Picking <b>%s</b> for %s.") % (
                    transfer.source_warehouse_id.name,
                    user.name,
                    issue_sudo.name,
                    transfer.receive_picking_id.name if transfer.receive_picking_id else '-',
                    transfer.dest_warehouse_id.name,
                )
            )

    def action_receive(self):
        """
        STEP 3 — Destination warehouse staff confirms items have been physically received.
        Only users belonging to the destination warehouse (via allowed_warehouse_ids) can do this.
        Validates the Receive Picking: Transit Location -> Destination/Stock.
        """
        for transfer in self:
            user = self.env.user
            allowed_whs = user.allowed_warehouse_ids
            if allowed_whs and transfer.dest_warehouse_id not in allowed_whs:
                raise ValidationError(
                    _("Only staff from '%s' can confirm receipt for this transfer.") % transfer.dest_warehouse_id.name
                )

            receive_picking = transfer.receive_picking_id or transfer.picking_id
            if not receive_picking:
                raise ValidationError(_("No receive stock picking found for this transfer."))

            receive_sudo = receive_picking.sudo()
            if receive_sudo.state not in ('done', 'cancel'):
                for move in receive_sudo.move_ids:
                    if move.state not in ('done', 'cancel'):
                        move.quantity = move.product_uom_qty
                        move.picked = True
                receive_sudo.button_validate()

            transfer.sudo().write({
                'state': 'received',
                'received_by_id': user.id,
                'received_date': fields.Datetime.now(),
            })
            transfer.message_post(
                body=_("✅ Items received at <b>%s</b> by %s. Receive picking <b>%s</b> validated. Transfer completed.") % (
                    transfer.dest_warehouse_id.name,
                    user.name,
                    receive_sudo.name,
                )
            )

    def action_cancel(self):
        for transfer in self:
            if transfer.state == 'received':
                raise ValidationError(_("A completed (Received) transfer cannot be cancelled."))
            if transfer.state == 'in_transit':
                raise ValidationError(
                    _("Cannot cancel transfer '%s' because goods have already been dispatched from '%s' and are currently In Transit. "
                      "Please complete the receipt at '%s' or arrange a return transfer.") % (
                        transfer.name,
                        transfer.source_warehouse_id.name,
                        transfer.dest_warehouse_id.name,
                    )
                )
            if transfer.issue_picking_id and transfer.issue_picking_id.state not in ('done', 'cancel'):
                transfer.issue_picking_id.sudo().action_cancel()
            if transfer.receive_picking_id and transfer.receive_picking_id.state not in ('done', 'cancel'):
                transfer.receive_picking_id.sudo().action_cancel()
            if transfer.picking_id and transfer.picking_id.state not in ('done', 'cancel'):
                transfer.picking_id.sudo().action_cancel()
            transfer.sudo().write({'state': 'cancel'})

    def action_view_issue_picking(self):
        self.ensure_one()
        if not self.issue_picking_id:
            raise ValidationError(_("No issue picking found."))
        return {
            'name': _('Issue Picking - %s') % (self.source_warehouse_id.name),
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'res_id': self.issue_picking_id.id,
            'type': 'ir.actions.act_window',
        }

    def action_view_receive_picking(self):
        self.ensure_one()
        if not self.receive_picking_id:
            raise ValidationError(_("No receive picking found."))
        return {
            'name': _('Receive Picking - %s') % (self.dest_warehouse_id.name),
            'view_mode': 'form',
            'res_model': 'stock.picking',
            'res_id': self.receive_picking_id.id,
            'type': 'ir.actions.act_window',
        }

    def action_view_picking(self):
        self.ensure_one()
        pickings = self.picking_ids
        if len(pickings) == 1:
            return {
                'name': _('Stock Transfer'),
                'view_mode': 'form',
                'res_model': 'stock.picking',
                'res_id': pickings.id,
                'type': 'ir.actions.act_window',
            }
        return {
            'name': _('Stock Pickings'),
            'view_mode': 'list,form',
            'res_model': 'stock.picking',
            'domain': [('id', 'in', pickings.ids)],
            'type': 'ir.actions.act_window',
        }

    def action_print_transfer_slip(self):
        """Prints official PDF Location Stock Transfer Slip / Waybill."""
        self.ensure_one()
        return self.env.ref('ibms_product.action_report_stock_location_transfer').report_action(self)



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

    image_1920 = fields.Image(
        string='Image',
        related='product_id.image_1920',
        readonly=True,
    )

    image_128 = fields.Image(
        string='Image (Small)',
        related='product_id.image_128',
        readonly=True,
    )

    default_code = fields.Char(
        string='Product Code',
        related='product_id.default_code',
        readonly=True,
    )

    part_number = fields.Char(
        string='Part Number',
        related='product_id.part_number',
        readonly=True,
    )

    secondary_parts_display = fields.Char(
        string='Secondary Part Numbers',
        related='product_id.secondary_parts_display',
        readonly=True,
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

