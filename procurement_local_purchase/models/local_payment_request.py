from odoo import models, fields, api, _
from odoo.exceptions import UserError

class LocalPaymentRequest(models.Model):
    _name = 'local.payment.request'
    _description = 'Payment Request Without PO'
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
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Pay To',
        tracking=True
    )
    payment_type = fields.Selection([
        ('withoutpo', 'Withoutpo'),
        ('advance', 'Advance'),
        ('final', 'Final Payment'),
    ], string='Payment Type', default='withoutpo', required=True, tracking=True)

    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
        ondelete='set null'
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        store=True,
        tracking=True
    )
    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        tracking=True
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        tracking=True
    )
    purpose = fields.Char(string='Purpose', tracking=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )


    payment_due_date = fields.Date(string='Payment Due Date', tracking=True)

    total_amount = fields.Float(string='Total Amount', tracking=True)

    amount_in_word = fields.Char(string='Amount in Word', tracking=True)

    budget_category_id = fields.Many2one(
        'account.budget.post',
        string='Budgetary Position',
        tracking=True
    )
    budget_account_id = fields.Many2one(
        'account.account',
        string='Budget Account',
        tracking=True
    )
    remaining_balance = fields.Float(string='Remaining Balance', tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('budget_approved', 'Budget Approved'),
        ('authorized', 'Authorized'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True)

    by_department = fields.Boolean(string='By Department', default=True)

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self):
        if self.purchase_order_id:
            self.partner_id = self.purchase_order_id.partner_id

    @api.onchange('total_amount')
    def _onchange_total_amount(self):
        for rec in self:
            if rec.total_amount:
                rec.amount_in_word = rec.company_id.currency_id.amount_to_text(rec.total_amount)
            else:
                rec.amount_in_word = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('local.payment.request') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_budget_approve(self):
        self.write({'state': 'budget_approved'})

    def action_authorize(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Please specify the partner (Pay To) before authorizing."))
        
        # Create Payment
        payment_vals = {
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': self.total_amount,
            'currency_id': self.company_id.currency_id.id,
            'date': fields.Date.today(),
            'memo': self.purpose or self.name,
        }
        payment = self.env['account.payment'].create(payment_vals)
        self.write({'state': 'authorized', 'payment_id': payment.id})

    def action_view_payment(self):
        self.ensure_one()
        if not self.payment_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment'),
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
        }

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_pay(self):
        self.write({'state': 'paid'})

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for payment in self:
            payment_request = self.env['local.payment.request'].sudo().search([('payment_id', '=', payment.id)], limit=1)
            if payment_request:
                payment_request.sudo().write({'state': 'paid'})
        return res
