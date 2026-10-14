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
    sale_type = fields.Selection([
        ('cash', 'Cash Sale'),
        ('credit', 'Credit Sale'),
    ], string='Sale Type', default='cash', required=True, tracking=True,
       help="Specifies whether this order is a Cash Sale (requiring payment proof/reference) or a Credit Sale (subject to customer credit checks).")
    partner_credit_status = fields.Selection(
        related='partner_id.credit_status',
        string='Customer Credit Status',
        readonly=True,
    )
    apply_order_discount = fields.Boolean(
        string='Order Discount',
        default=False,
        tracking=True,
        help="Check to apply a global discount across all products.",
    )
    order_discount_percent = fields.Float(
        string='Discount (%)',
        default=0.0,
        digits=(16, 2),
        tracking=True,
        help="Global discount percentage applied to all products combined.",
    )
    order_discount_amount = fields.Monetary(
        string='Discount Amount',
        compute='_compute_order_discount_amount',
        currency_field='currency_id',
    )
    gross_amount_untaxed = fields.Monetary(
        string='Gross Subtotal',
        compute='_compute_order_discount_amount',
        currency_field='currency_id',
    )
    max_discount = fields.Float(
        string='Max Discount (%)',
        compute='_compute_discount_approval',
        store=True,
        tracking=True,
        help="Highest discount percentage given on this order (global or line-level).",
    )
    has_excessive_discount = fields.Boolean(
        string='Discount > 5%',
        compute='_compute_discount_approval',
        store=True,
        help="True if the global discount or any product line discount exceeds 5%.",
    )
    is_sales_manager = fields.Boolean(
        compute='_compute_is_sales_manager',
        string='Is Sales Manager',
    )

    def _compute_is_sales_manager(self):
        is_mgr = self.env.user.has_group('sales_team.group_sale_manager')
        for order in self:
            order.is_sales_manager = is_mgr

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.discount', 'order_line.price_subtotal', 'order_line.product_id')
    def _compute_discount_approval(self):
        for order in self:
            line_discounts = [
                line.discount for line in order.order_line
                if line.product_id and not line.display_type and not line.is_downpayment
            ]
            max_line_disc = max(line_discounts) if line_discounts else 0.0

            global_disc = order.order_discount_percent if order.apply_order_discount else 0.0
            eff_max = max(global_disc, max_line_disc)
            order.max_discount = eff_max
            order.has_excessive_discount = eff_max > 5.0

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal')
    def _compute_order_discount_amount(self):
        for order in self:
            regular_lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
            gross = sum(regular_lines.mapped('price_subtotal'))
            order.gross_amount_untaxed = gross
            if order.apply_order_discount and order.order_discount_percent > 0:
                order.order_discount_amount = -round(gross * (order.order_discount_percent / 100.0), 2)
            else:
                order.order_discount_amount = 0.0

    @api.onchange('apply_order_discount')
    def _onchange_apply_order_discount(self):
        if not self.apply_order_discount:
            self.order_discount_percent = 0.0

    def write(self, vals):
        res = super().write(vals)
        if 'apply_order_discount' in vals or 'order_discount_percent' in vals:
            for order in self:
                order._apply_global_discount()
        return res

    def _get_or_create_discount_product(self):
        company = self.company_id or self.env.company
        discount_product = company.sale_discount_product_id
        if not discount_product:
            discount_product = self.env['product.product'].search([('default_code', '=', 'DISC')], limit=1)
            if not discount_product:
                discount_product = self.env['product.product'].create({
                    'name': 'Discount',
                    'type': 'service',
                    'default_code': 'DISC',
                    'part_number': 'DISC',
                    'invoice_policy': 'order',
                    'list_price': 0.0,
                    'company_id': company.id,
                })
            company.sale_discount_product_id = discount_product
        return discount_product

    def action_apply_global_discount(self):
        for order in self:
            order._apply_global_discount()

    def action_remove_global_discount(self):
        for order in self:
            order.apply_order_discount = False
            order.order_discount_percent = 0.0
            order._apply_global_discount()

    def _apply_global_discount(self):
        # In Option B, clean up any discount products from order lines table
        for order in self:
            disc_lines = order.order_line.filtered(
                lambda l: (l.product_id and l.product_id.default_code == 'DISC') or getattr(l, 'is_discount_line', False) or l.price_unit < 0
            )
            if disc_lines:
                disc_lines.unlink()

    @api.depends_context('lang')
    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_tax_totals(self):
        AccountTax = self.env['account.tax']
        for order in self:
            order_lines = order._get_priced_lines()
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            base_lines += order._add_base_lines_for_early_payment_discount()

            if order.apply_order_discount and order.order_discount_percent > 0 and base_lines:
                AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
                discount_product = order._get_or_create_discount_product()
                def grouping_function(base_line):
                    return {'product_id': discount_product}
                disc_base_lines = AccountTax._prepare_global_discount_lines(
                    base_lines=base_lines,
                    company=order.company_id,
                    amount_type='percent',
                    amount=order.order_discount_percent,
                    computation_key=f'global_discount,{order.id}',
                    grouping_function=grouping_function,
                )
                base_lines = base_lines + disc_base_lines

            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            order.tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_id.currency_id,
                company=order.company_id,
            )

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal')
    def _compute_amounts(self):
        AccountTax = self.env['account.tax']
        for order in self:
            order_lines = order._get_priced_lines()
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
            base_lines += order._add_base_lines_for_early_payment_discount()

            if order.apply_order_discount and order.order_discount_percent > 0 and base_lines:
                AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
                discount_product = order._get_or_create_discount_product()
                def grouping_function(base_line):
                    return {'product_id': discount_product}
                disc_base_lines = AccountTax._prepare_global_discount_lines(
                    base_lines=base_lines,
                    company=order.company_id,
                    amount_type='percent',
                    amount=order.order_discount_percent,
                    computation_key=f'global_discount,{order.id}',
                    grouping_function=grouping_function,
                )
                base_lines = base_lines + disc_base_lines

            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_id.currency_id,
                company=order.company_id,
            )
            order.amount_untaxed = tax_totals['base_amount_currency']
            order.amount_tax = tax_totals['tax_amount_currency']
            order.amount_total = tax_totals['total_amount_currency']

    @api.onchange('payment_term_id')
    def _onchange_payment_term_id_sale_type(self):
        if self.payment_term_id:
            has_credit = False
            if hasattr(self.payment_term_id, 'line_ids'):
                for line in self.payment_term_id.line_ids:
                    if (getattr(line, 'nb_days', 0) or 0) > 0 or getattr(line, 'delay_type', '') != 'days_after':
                        has_credit = True
                        break
            self.sale_type = 'credit' if has_credit else 'cash'

    def action_submit_approval(self):
        for order in self:
            if not order.order_line:
                raise UserError(_("You cannot submit an empty quotation for approval. Please add products first."))
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit':
                partner = order.partner_id
                if partner and getattr(partner, 'credit_status', False) == 'blocked':
                    due_amt = getattr(partner, 'due_amount', 0.0)
                    limit = getattr(partner, 'blocking_stage', 0.0)
                    raise UserError(_(
                        "Customer '%s' has a BLOCKED credit status (Due: %.2f, Blocking limit: %.2f). "
                        "Credit sales cannot be submitted for this customer."
                    ) % (partner.name, due_amt, limit))
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
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit':
                partner = order.partner_id
                if partner and getattr(partner, 'credit_status', False) == 'blocked':
                    raise UserError(_(
                        "Customer '%s' has a BLOCKED credit status. Credit sales cannot be approved."
                    ) % partner.name)
            elif order.sale_type == 'cash':
                if not order.payment_proof and not order.payment_note:
                    raise UserError(_(
                        "For Cash Sales, please provide Payment Proof / Receipt or Payment Note / Reference before approving."
                    ))
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
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit' and order.partner_id and getattr(order.partner_id, 'credit_status', False) == 'blocked':
                raise UserError(_("Customer '%s' has a BLOCKED credit status. Credit sales cannot be confirmed.") % order.partner_id.name)
            if order.sale_type == 'cash' and not order.payment_proof and not order.payment_note:
                raise UserError(_("For Cash Sales, please provide Payment Proof / Receipt or Payment Note / Reference before confirming."))
            if order.has_excessive_discount and not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_(
                    "This order has a discount of %(disc).2f%% which exceeds the 5.0%% limit allowed for salespeople. "
                    "Please click 'Submit for Approval' to request Manager Approval."
                ) % {'disc': order.max_discount})
        return super().action_confirm()

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.payment_proof:
            invoice_vals['payment_proof'] = self.payment_proof
            invoice_vals['payment_proof_filename'] = self.payment_proof_filename
        if self.payment_note:
            invoice_vals['payment_note'] = self.payment_note
        if hasattr(self, 'sale_type') and self.sale_type:
            invoice_vals['sale_type'] = self.sale_type

        # Option B: Add the discount line to invoice lines so invoice balances
        if self.apply_order_discount and self.order_discount_percent > 0:
            discount_product = self._get_or_create_discount_product()
            AccountTax = self.env['account.tax']
            base_lines = [line._prepare_base_line_for_taxes_computation() for line in self._get_priced_lines()]
            if base_lines:
                AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
                def grouping_function(base_line):
                    return {'product_id': discount_product}
                global_discount_base_lines = AccountTax._prepare_global_discount_lines(
                    base_lines=base_lines,
                    company=self.company_id,
                    amount_type='percent',
                    amount=self.order_discount_percent,
                    computation_key=f'global_discount,{self.id}',
                    grouping_function=grouping_function,
                )
                for base_line in global_discount_base_lines:
                    invoice_vals.setdefault('invoice_line_ids', []).append(fields.Command.create({
                        'name': _("Order Discount (%(percent).2f%%)") % {'percent': self.order_discount_percent},
                        'product_id': discount_product.id,
                        'price_unit': base_line['price_unit'],
                        'quantity': base_line['quantity'],
                        'tax_ids': [fields.Command.set(base_line['tax_ids'].ids)],
                        'sequence': 999,
                    }))
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

    is_discount_line = fields.Boolean(
        string='Is Discount Line',
        default=False,
        copy=False,
    )
    part_number = fields.Char(
        string='Part Number',
        compute='_compute_part_number',
        store=True,
        readonly=True,
        copy=False,
    )

    @api.depends('product_id', 'product_template_id')
    def _compute_part_number(self):
        for line in self:
            line.part_number = (
                (line.product_id and line.product_id.part_number)
                or (line.product_template_id and line.product_template_id.part_number)
                or False
            )

    @api.onchange('product_id', 'product_template_id')
    def _onchange_product_part_number(self):
        self.part_number = (
            (self.product_id and self.product_id.part_number)
            or (self.product_template_id and self.product_template_id.part_number)
            or False
        )

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
