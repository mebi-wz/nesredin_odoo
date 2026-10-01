from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ForeignPaymentRequest(models.Model):
    _name = 'foreign.payment.request'
    _description = 'Foreign Payment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        tracking=True
    )
    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
        ondelete='set null'
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        tracking=True
    )

    # Payment Details
    payment_type = fields.Selection([
        ('landed_cost', 'Landed Cost Payment'),
    ], string='Payment Type', default='landed_cost',required=True, tracking=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True
    )
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True, tracking=True)
    exchange_rate = fields.Float(string='Exchange Rate', default=1.0, tracking=True)
    amount_etb = fields.Float(
        string='Amount (ETB)',
        compute='_compute_amount_etb',
        store=True,
        tracking=True
    )

    bank_id = fields.Many2one('res.bank', string='Bank', tracking=True)
    payment_reference = fields.Char(string='Payment Reference', tracking=True)
    payment_date = fields.Date(string='Payment Date', tracking=True)
    due_date = fields.Date(string='Due Date', tracking=True)
    description = fields.Text(string='Description', tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    line_ids = fields.One2many(
        'foreign.payment.request.line',
        'payment_request_id',
        string='Payment Lines'
    )

    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self):
        if self.purchase_order_id:
            self.vendor_id = self.purchase_order_id.partner_id
            self.currency_id = self.purchase_order_id.currency_id
            self.exchange_rate = self.purchase_order_id.currency_rate or 1.0

    @api.depends('line_ids.amount')
    def _compute_amount(self):
        for rec in self:
            rec.amount = sum(rec.line_ids.mapped('amount'))

    @api.depends('amount', 'exchange_rate')
    def _compute_amount_etb(self):
        for rec in self:
            rec.amount_etb = rec.amount * rec.exchange_rate

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-populate fields from PO if not provided (relevant for tests and API)
            if vals.get('purchase_order_id') and (not vals.get('vendor_id') or not vals.get('currency_id')):
                po = self.env['purchase.order'].browse(vals['purchase_order_id'])
                if not vals.get('vendor_id'):
                    vals['vendor_id'] = po.partner_id.id
                if not vals.get('currency_id'):
                    vals['currency_id'] = po.currency_id.id

            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('foreign.payment.request') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        if not self.line_ids:
            raise UserError(_("Please add at least one line before submitting."))
        self.write({'state': 'submitted'})
        self._notify_next_approver('submitted')

    def action_approve(self):
        self.ensure_one()
        # Create Vendor Bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_date_due': fields.Date.today(),
            'currency_id': self.currency_id.id,
            'invoice_origin': self.purchase_order_id.name,
            'purchase_id': self.purchase_order_id.id,
            'company_id': self.company_id.id,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.description or line.product_id.display_name,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'purchase_line_id': False, # Manual lines for landed costs/others
                    'is_landed_costs_line': line.product_id.landed_cost_ok, 
                })
                for line in self.line_ids
            ],
        }
        bill = self.env['account.move'].create(bill_vals)
        self.write({'state': 'approved', 'vendor_bill_id': bill.id})

        # Sync with existing draft Landed Cost if present
        if self.purchase_order_id:
            draft_landed_cost = self.env['stock.landed.cost'].search([
                ('picking_ids', 'in', self.purchase_order_id.picking_ids.ids),
                ('state', '=', 'draft')
            ], limit=1)
            if draft_landed_cost:
                if not draft_landed_cost.vendor_bill_id:
                    draft_landed_cost.write({'vendor_bill_id': bill.id})
                
                new_cost_lines = []
                for line in self.line_ids:
                    if line.product_id and line.product_id.landed_cost_ok:
                        bill_line = bill.invoice_line_ids.filtered(lambda l: l.product_id == line.product_id)[:1]
                        if bill_line and bill_line.account_id:
                            account_id = bill_line.account_id.id
                        else:
                            account_id = line.product_id.property_account_expense_id.id or line.product_id.categ_id.property_account_expense_categ_id.id
                        
                        new_cost_lines.append((0, 0, {
                            'product_id': line.product_id.id,
                            'name': line.description or line.product_id.name,
                            'account_id': account_id,
                            'split_method': 'by_customs_amount',
                            'price_unit': line.amount,
                        }))
                if new_cost_lines:
                    draft_landed_cost.write({'cost_lines': new_cost_lines})

        self._notify_next_approver('approved')

    def action_pay(self):
        self.write({
            'state': 'paid',
            'payment_date': fields.Date.today(),
        })
        self._notify_next_approver('paid')

    def action_cancel(self):
        for rec in self:
            if rec.vendor_bill_id and rec.vendor_bill_id.state != 'cancel':
                raise UserError(_("You cannot cancel this payment request because it has a Vendor Bill that is not cancelled. Please cancel the bill first."))
        self.write({'state': 'cancelled'})
        self._notify_next_approver('cancelled')

    def unlink(self):
        for rec in self:
            if rec.vendor_bill_id:
                raise UserError(_("You cannot delete a payment request that has an associated Vendor Bill."))
        return super(ForeignPaymentRequest, self).unlink()

    def action_draft(self):
        self.write({'state': 'draft'})
        self._notify_next_approver('draft')

    def _notify_next_approver(self, next_state):
        # Clear old activities for this record first
        self.activity_unlink(['mail.mail_activity_data_todo'])

        # Notify requester of the update
        requester_user = self.requested_by if self.requested_by else self.create_uid
        if requester_user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester_user.id,
                summary=_("Payment Request Update: %s") % self.name,
                note=_("Your payment request (%s) is now in state: %s.") % (self.name, next_state.replace('_', ' ').replace('-', ' ').capitalize())
            )

        group_xmlid_map = {
            'submitted': 'account.group_account_invoice',
            'approved': 'account.group_account_invoice',
        }
        
        group_xmlid = group_xmlid_map.get(next_state)
        if not group_xmlid:
            return

        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        company_id = self.sudo().company_id.id
        users = group.sudo().user_ids.filtered(lambda u: u.company_id.id == company_id or company_id in u.company_ids.ids)
        if not users:
            return

        for user in users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_("Payment Request Action Required"),
                note=_("Payment Request (%s) is awaiting your action (State: %s).") % (self.name, next_state)
            )

    def action_view_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
        }

class ForeignPaymentRequestLine(models.Model):
    _name = 'foreign.payment.request.line'
    _description = 'Foreign Payment Request Line'

    payment_request_id = fields.Many2one(
        'foreign.payment.request',
        string='Payment Request',
        ondelete='cascade',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('landed_cost_ok', '=', True)]
    )
    description = fields.Char(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='payment_request_id.company_id',
        store=True,
        readonly=True
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.price_unit = self.product_id.standard_price

    @api.depends('quantity', 'price_unit')
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.price_unit
