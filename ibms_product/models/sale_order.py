# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(
        selection_add=[('to_approve', 'Waiting Approval')],
        ondelete={'to_approve': 'set default'},
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        copy=False,
        readonly=True,
        tracking=True,
        help="Manager who approved this sales order.",
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        copy=False,
        readonly=True,
        tracking=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        copy=False,
        readonly=True,
        tracking=True,
        help="Reason provided by the manager when rejecting this order.",
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Location',
        check_company=True,
        copy=False,
        help="Location / Branch cost center for this order.",
    )
    payment_proof = fields.Binary(
        string='Payment Proof / Receipt',
        attachment=True,
        copy=False,
        help="Upload payment screenshot, bank transfer slip, Telebirr/CBE Birr confirmation, or receipt.",
    )
    payment_proof_filename = fields.Char(string='Payment Proof Filename', copy=False)
    payment_note = fields.Char(
        string='Payment Note / Reference',
        copy=False,
        help="Add notes about the payment, e.g. Transaction ID, bank deposit reference, Telebirr/CBE Birr confirmation code, etc.",
    )

    def action_submit_approval(self):
        for order in self:
            if not order.order_line:
                raise UserError(_("You cannot submit an empty quotation for approval. Please add products first."))
            order.write({
                'state': 'to_approve',
                'rejection_reason': False,
            })
            order.message_post(
                body=_("Quotation submitted for manager approval by %s.") % self.env.user.name,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

    def action_approve(self):
        for order in self:
            if not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_("Only Sales Managers can approve sales orders."))
            order.write({
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
                'rejection_reason': False,
            })
            order.message_post(
                body=_("<b>Order Approved</b> by %s.") % self.env.user.name,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            order.action_confirm()

    def action_reject_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only Sales Managers can reject sales orders."))
        return {
            'name': _('Reject Sales Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _confirmation_error_message(self):
        self.ensure_one()
        if self.state == 'to_approve':
            if any(
                not line.display_type
                and not line.is_downpayment
                and not line.product_id
                for line in self.order_line
            ):
                return _("Some order lines are missing a product, you need to correct them before going further.")
            return False
        return super()._confirmation_error_message()

    def action_confirm(self):
        for order in self:
            if not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_("Sales Orders require approval from a Sales Manager before confirmation. Please click 'Submit for Approval'."))
        return super().action_confirm()

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.payment_proof:
            invoice_vals['payment_proof'] = self.payment_proof
            invoice_vals['payment_proof_filename'] = self.payment_proof_filename
        if self.payment_note:
            invoice_vals['payment_note'] = self.payment_note
        return invoice_vals

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'warehouse_id' in fields_list and not res.get('warehouse_id'):
            if self.env.user.default_warehouse_id:
                res['warehouse_id'] = self.env.user.default_warehouse_id.id
            elif self.env.user.allowed_warehouse_ids:
                res['warehouse_id'] = self.env.user.allowed_warehouse_ids[0].id
        if res.get('warehouse_id') and 'analytic_account_id' in fields_list and not res.get('analytic_account_id'):
            warehouse = self.env['stock.warehouse'].browse(res['warehouse_id'])
            if warehouse.analytic_account_id:
                res['analytic_account_id'] = warehouse.analytic_account_id.id
        return res

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.analytic_account_id.id),
                ('company_id', '=', self.company_id.id)
            ])
            if self.warehouse_id and self.warehouse_id not in warehouses:
                self.warehouse_id = False
            if len(warehouses) == 1:
                self.warehouse_id = warehouses[0].id
            elif not warehouses:
                self.warehouse_id = False

            acc_str = str(self.analytic_account_id.id)
            for line in self.order_line:
                if not line.display_type:
                    line.analytic_distribution = {acc_str: 100.0}
        else:
            self.warehouse_id = False

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id_analytic(self):
        if self.warehouse_id and self.warehouse_id.analytic_account_id:
            self.analytic_account_id = self.warehouse_id.analytic_account_id.id

    @api.onchange('partner_id')
    def _onchange_partner_id_update_prices(self):
        for line in self.order_line:
            if line.product_id and not line.is_downpayment:
                line._reset_price_unit()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_id_set_analytic(self):
        if self.order_id.analytic_account_id and not self.analytic_distribution:
            self.analytic_distribution = {str(self.order_id.analytic_account_id.id): 100.0}

    def _get_display_price_ignore_combo(self):
        self.ensure_one()
        partner = self.order_id.partner_id.commercial_partner_id or self.order_id.partner_id
        if partner and partner.customer_type == 'wholesaler' and self.product_id and self.product_id.wholesale_price > 0:
            price = self.product_id.wholesale_price
            if self.product_uom_id and self.product_id.uom_id and self.product_uom_id != self.product_id.uom_id:
                price = self.product_id.uom_id._compute_price(price, self.product_uom_id)
            return price
        return super()._get_display_price_ignore_combo()
