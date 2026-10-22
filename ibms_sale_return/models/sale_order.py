# -*- coding: utf-8 -*-
from collections import defaultdict
from markupsafe import Markup
from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_return = fields.Boolean(
        string='Is Sales Return',
        default=False,
        copy=False,
        tracking=True,
        help="Indicates whether this order is a Return Sales Order.",
    )
    original_sale_order_id = fields.Many2one(
        'sale.order',
        string='Original Sales Order',
        copy=False,
        tracking=True,
        domain="[('state', 'in', ('sale', 'done')), ('is_return', '=', False)]",
        help="The original Sales Order being returned.",
    )
    original_invoice_id = fields.Many2one(
        'account.move',
        string='Original Invoice',
        copy=False,
        tracking=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
        help="The original customer invoice being credited / reversed.",
    )
    return_order_ids = fields.One2many(
        'sale.order',
        'original_sale_order_id',
        string='Return Orders',
        help="Return orders created against this sales order.",
    )
    return_count = fields.Integer(
        string='Return Count',
        compute='_compute_return_count',
    )
    return_reason = fields.Char(
        string='Return Reason',
        copy=False,
        tracking=True,
    )
    can_return_sale = fields.Boolean(
        string='Can Return Sale',
        compute='_compute_can_return_sale',
        help="Indicates whether this order can have a return initiated (requires confirmed delivery and confirmed invoice).",
    )

    @api.depends('return_order_ids')
    def _compute_return_count(self):
        for order in self:
            order.return_count = len(order.return_order_ids)

    @api.depends(
        'state', 'is_return',
        'invoice_ids.state', 'invoice_ids.move_type',
        'picking_ids.state', 'picking_ids.picking_type_code',
        'order_line.qty_delivered', 'order_line.product_id',
    )
    def _compute_can_return_sale(self):
        for order in self:
            if order.is_return or order.state not in ('sale', 'done'):
                order.can_return_sale = False
                continue

            # 1. Must have at least one confirmed/posted customer invoice
            has_confirmed_invoice = any(
                inv.move_type == 'out_invoice' and inv.state == 'posted'
                for inv in order.invoice_ids
            )

            # 2. Must have at least one confirmed/done delivery (for stockable lines)
            has_stock_lines = any(
                not l.display_type and l.product_id.type != 'service'
                for l in order.order_line
            )
            if has_stock_lines:
                has_confirmed_delivery = any(
                    p.picking_type_code == 'outgoing' and p.state == 'done'
                    for p in order.picking_ids
                )
            else:
                has_confirmed_delivery = any(l.qty_delivered > 0 for l in order.order_line)

            order.can_return_sale = has_confirmed_invoice and has_confirmed_delivery

    def action_open_return_wizard(self):
        self.ensure_one()
        if self.is_return:
            raise UserError(_("You cannot create a return from a return order."))
        if self.state not in ('sale', 'done'):
            raise UserError(_("Returns can only be initiated on confirmed Sales Orders."))

        has_confirmed_invoice = any(
            inv.move_type == 'out_invoice' and inv.state == 'posted'
            for inv in self.invoice_ids
        )
        if not has_confirmed_invoice:
            raise UserError(_("A sales return can only be initiated after the customer invoice is confirmed (posted)."))

        has_stock_lines = any(
            not l.display_type and l.product_id.type != 'service'
            for l in self.order_line
        )
        if has_stock_lines:
            has_confirmed_delivery = any(
                p.picking_type_code == 'outgoing' and p.state == 'done'
                for p in self.picking_ids
            )
            if not has_confirmed_delivery:
                raise UserError(_("A sales return can only be initiated after delivery is confirmed (done)."))

        return {
            'name': _('Return Sales Order - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            },
        }

    def action_view_returns(self):
        self.ensure_one()
        returns = self.return_order_ids
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_orders')
        if len(returns) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = returns.id
        else:
            action['domain'] = [('id', 'in', returns.ids)]
            action['context'] = {'default_is_return': True}
        return action

    def _action_confirm(self):
        return_orders = self.filtered('is_return')
        standard_orders = self - return_orders

        # Confirm standard orders normally
        res = super(SaleOrder, standard_orders)._action_confirm()

        # For return orders: confirm, then auto-create draft return picking and draft credit note
        for order in return_orders:
            super(SaleOrder, order)._action_confirm()
            # 1. Automatically create draft incoming return delivery for storekeeper receipt
            order._create_draft_return_picking()
            # 2. Automatically create draft return invoice (customer credit note) for accounting
            order._create_draft_return_invoice()

        return res

    def _create_draft_return_picking(self):
        self.ensure_one()
        if not self.is_return:
            return False

        orig_order = self.original_sale_order_id
        if not orig_order:
            return False

        # Find original delivery (outgoing picking)
        orig_pickings = orig_order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        done_pickings = orig_pickings.filtered(lambda p: p.state == 'done')
        target_picking = done_pickings[:1] or orig_pickings[:1]

        warehouse = (
            self.warehouse_id
            or (target_picking and target_picking.warehouse_id)
            or self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        )
        if not warehouse:
            return False

        # Use dedicated "Returned from Sales" operation type (Receipt)
        picking_type = warehouse._get_or_create_sale_return_type()
        if not picking_type and target_picking and target_picking.picking_type_id.return_picking_type_id:
            picking_type = target_picking.picking_type_id.return_picking_type_id
        if not picking_type:
            picking_type = warehouse.in_type_id

        # Source is customer location, destination is warehouse stock
        location_id = (
            target_picking.location_dest_id
            if target_picking
            else (picking_type.default_location_src_id or self.partner_id.property_stock_customer)
        )
        location_dest_id = picking_type.default_location_dest_id or warehouse.lot_stock_id

        picking_vals = {
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'origin': _("Return of %s (%s)") % (orig_order.name, self.name),
            'location_id': location_id.id,
            'location_dest_id': location_dest_id.id,
            'sale_id': self.id,
            'return_id': target_picking.id if target_picking else False,
            'company_id': self.company_id.id,
        }
        return_picking = self.env['stock.picking'].create(picking_vals)

        for line in self.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0 and l.product_id.type != 'service'
        ):
            orig_move = False
            if target_picking:
                orig_move = target_picking.move_ids.filtered(
                    lambda m: m.product_id == line.product_id and m.state == 'done'
                )[:1]

            move_vals = {
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': (line.product_uom_id or line.product_id.uom_id).id,
                'picking_id': return_picking.id,
                'location_id': location_id.id,
                'location_dest_id': location_dest_id.id,
                'picking_type_id': picking_type.id,
                'warehouse_id': warehouse.id,
                'origin_returned_move_id': orig_move.id if orig_move else False,
                'sale_line_id': line.id,
                'company_id': self.company_id.id,
            }
            if 'description_picking' in self.env['stock.move']._fields:
                move_vals['description_picking'] = _("Return of %s") % line.name
            if 'name' in self.env['stock.move']._fields:
                move_vals['name'] = _("Return of %s") % line.name
            self.env['stock.move'].create(move_vals)

        # Confirm and assign the incoming return receipt so it is Ready and shows on the Inventory Overview card
        return_picking.action_confirm()
        return_picking.action_assign()

        try:
            picking_link = return_picking._get_html_link()
        except Exception:
            picking_link = Markup("<b>%s</b>") % return_picking.name

        self.message_post(
            body=Markup(
                _("Return Receipt %s created automatically under operation type '%s' (Ready for receipt validation).")
                % (picking_link, picking_type.name)
            )
        )
        return return_picking

    def _create_draft_return_invoice(self):
        """Creates a Return Invoice (Customer Credit Note - out_refund) linked to the original invoice."""
        self.ensure_one()
        if not self.is_return:
            return False

        # If a non-cancelled invoice already exists for this return order, return it
        existing_invoices = self.invoice_ids.filtered(lambda m: m.state != 'cancel')
        if existing_invoices:
            return existing_invoices[0]

        orig_invoice = self.original_invoice_id
        if not orig_invoice and self.original_sale_order_id:
            posted_invoices = self.original_sale_order_id.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            )
            orig_invoice = posted_invoices[:1]

        refund_journal = (
            (orig_invoice and orig_invoice.journal_id)
            or self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        )

        orig_so_name = self.original_sale_order_id.name if self.original_sale_order_id else _("N/A")
        ref_text = _("Return of %s (Original: %s)") % (self.name, orig_so_name)
        if self.return_reason:
            ref_text += _(" - %s") % self.return_reason

        move_vals = {
            'move_type': 'out_refund',  # Customer Credit Note (Return Invoice)
            'journal_id': refund_journal.id if refund_journal else False,
            'partner_id': self.partner_invoice_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'ref': ref_text,
            'reversed_entry_id': orig_invoice.id if orig_invoice else False,
            'sale_return_order_id': self.id,
            'invoice_line_ids': [],
        }

        if orig_invoice:
            if orig_invoice.fiscal_position_id:
                move_vals['fiscal_position_id'] = orig_invoice.fiscal_position_id.id
            if orig_invoice.invoice_payment_term_id:
                move_vals['invoice_payment_term_id'] = orig_invoice.invoice_payment_term_id.id

        if hasattr(self, 'sale_type') and self.sale_type:
            move_vals['sale_type'] = self.sale_type

        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_uom_qty > 0):
            line_vals = {
                'product_id': line.product_id.id,
                'name': line.name,
                'quantity': line.product_uom_qty,
                'product_uom_id': (line.product_uom_id or line.product_id.uom_id).id,
                'price_unit': line.price_unit,
                'discount': line.discount if hasattr(line, 'discount') else 0.0,
                'tax_ids': [Command.set((getattr(line, 'tax_ids', False) or getattr(line, 'tax_id', False) or self.env['account.tax']).ids)],
                'sale_line_ids': [Command.link(line.id)],
            }
            if line.analytic_distribution:
                line_vals['analytic_distribution'] = line.analytic_distribution
            move_vals['invoice_line_ids'].append(Command.create(line_vals))

        credit_note = self.env['account.move'].create(move_vals)

        try:
            credit_note_link = credit_note._get_html_link()
        except Exception:
            credit_note_link = Markup("<b>%s</b>") % credit_note.name

        self.message_post(
            body=Markup(
                _("Draft Return Invoice (Credit Note) %s created automatically upon approval.") % credit_note_link
            )
        )

        if orig_invoice:
            orig_invoice.message_post(
                body=Markup(
                    _("Draft Return Credit Note %s created from Sales Return Order <b>%s</b>.")
                    % (credit_note_link, self.name)
                )
            )

        return credit_note

    def action_create_return_invoice(self):
        """Creates or opens the Return Invoice (Customer Credit Note - out_refund)."""
        self.ensure_one()
        if not self.is_return:
            raise UserError(_("This action is only applicable to Sales Return Orders."))
        if self.state != 'sale':
            raise UserError(_("Please approve and confirm the return order before creating a return invoice."))

        existing_invoices = self.invoice_ids.filtered(lambda m: m.state != 'cancel')
        if existing_invoices:
            credit_note = existing_invoices[0]
        else:
            credit_note = self._create_draft_return_invoice()

        return {
            'name': _('Return Invoice (Credit Note)'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': credit_note.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_qty_invoiced(self):
        """On a return order, out_refund lines count positively towards invoiced quantities."""
        invoiced_qties = super()._prepare_qty_invoiced()
        return_lines = self.filtered(lambda l: l.order_id.is_return)
        for line in return_lines:
            qty = 0.0
            for invoice_line in line._get_invoice_lines():
                if invoice_line.move_id.state != 'cancel' or invoice_line.move_id.payment_state == 'invoicing_legacy':
                    invoice_qty = invoice_line.product_uom_id._compute_quantity(
                        invoice_line.quantity, line.product_uom_id, round=False
                    )
                    if invoice_line.move_id.move_type == 'out_refund':
                        qty += invoice_qty
                    elif invoice_line.move_id.move_type == 'out_invoice':
                        qty -= invoice_qty
            invoiced_qties[line] = qty
        return invoiced_qties

    @api.depends('invoice_lines.move_id.state', 'invoice_lines.quantity')
    def _compute_qty_invoiced_posted(self):
        super()._compute_qty_invoiced_posted()
        return_lines = self.filtered(lambda l: l.order_id.is_return)
        for line in return_lines:
            qty = 0.0
            for invoice_line in line._get_invoice_lines():
                if invoice_line.move_id.state == 'posted' or invoice_line.move_id.payment_state == 'invoicing_legacy':
                    invoice_qty = invoice_line.product_uom_id._compute_quantity(
                        invoice_line.quantity, line.product_uom_id
                    )
                    if invoice_line.move_id.move_type == 'out_refund':
                        qty += invoice_qty
                    elif invoice_line.move_id.move_type == 'out_invoice':
                        qty -= invoice_qty
            line.qty_invoiced_posted = qty

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        # Prevent standard outgoing procurement rules on return order lines
        lines_to_procure = self.filtered(lambda l: not l.order_id.is_return)
        if lines_to_procure:
            return super(SaleOrderLine, lines_to_procure)._action_launch_stock_rule(
                previous_product_uom_qty=previous_product_uom_qty
            )
        return True
