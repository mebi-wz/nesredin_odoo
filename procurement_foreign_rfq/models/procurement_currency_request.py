from odoo import models, fields, api, _

class CurrencyRequest(models.Model):
    _name = 'procurement.currency.request'
    _description = 'Foreign Currency Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    rfq_id = fields.Many2one(
        'foreign.rfq',
        string="RFQ",
        required=True,
        ondelete='cascade',
        tracking=True
    )

    requested_by = fields.Many2one(
        'res.users',
        string="Requested By",
        default=lambda self: self.env.user,
        tracking=True,
        ondelete='set null'
    )

    department_id = fields.Many2one(
        'hr.department',
        string="Department",
        store=True,
        tracking=True
    )

    date_request = fields.Datetime(
        string="Request Date",
        default=fields.Datetime.now,
        tracking=True
    )

    proforma_invoice = fields.Char(string="Proforma Invoice", tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company
    )

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        tracking=True
    )

    purpose = fields.Selection([
        ('refill', 'Refill'),
        ('payment', 'Payment')
    ], string="Purpose", tracking=True)

    nbe_id = fields.Many2one('nbe.config', string="NBE", tracking=True)

    supplier_id = fields.Many2one(
        'res.partner',
        string="Supplier",
        tracking=True
    )

    payment_due_date = fields.Date(string="Payment Due Date", tracking=True)

    total_amount_usd = fields.Float(string="Total Amount USD", tracking=True)

    exchange_rate = fields.Float(string="Exchange Rate", tracking=True)

    total_amount_etb = fields.Float(
        string="Total Amount ETB",
        compute="_compute_total_etb",
        store=True,
        tracking=True
    )

    amount_in_word = fields.Char(string="Amount in Word", tracking=True)

    approved_date = fields.Date(string="Approved Date", tracking=True)

    bank_id = fields.Many2one(
        'res.bank',
        string="Bank",
        tracking=True
    )

    branch = fields.Char(string="Branch", tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('progress', 'On Progress'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled')
    ], default='draft', string="Status", tracking=True)

    @api.depends('total_amount_usd', 'exchange_rate')
    def _compute_total_etb(self):
        for rec in self:
            rec.total_amount_etb = rec.total_amount_usd * rec.exchange_rate

    @api.onchange('total_amount_etb')
    def _onchange_amount_word(self):
        for rec in self:
            if rec.total_amount_etb:
                rec.amount_in_word = self.env.company.currency_id.amount_to_text(rec.total_amount_etb)
            else:
                rec.amount_in_word = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('procurement.currency.request') or _('New')
        return super().create(vals_list)

    def action_queue(self):
        self.write({'state': 'queued'})
        self._notify_next_approver('queued')

    def action_progress(self):
        self.write({'state': 'progress'})
        self._notify_next_approver('progress')

    def action_approve(self):
        self.write({'state': 'approved', 'approved_date': fields.Date.today()})
        self._notify_next_approver('approved')
        # Transition linked RFQ to 'approved' (currency approved) if it is pending currency
        if self.rfq_id and self.rfq_id.state == 'pending_currency':
            self.rfq_id.write({'state': 'approved'})
            self.rfq_id.message_post(
                body=_("Currency Request %s approved. RFQ is now ready for Purchase Order creation.") % self.name,
                message_type='notification'
            )

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self._notify_next_approver('cancelled')

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
                summary=_("Currency Request Update: %s") % self.name,
                note=_("Your currency request (%s) is now in state: %s.") % (self.name, next_state.replace('_', ' ').replace('-', ' ').capitalize())
            )

        group_xmlid_map = {
            'queued': 'account.group_account_invoice',
            'progress': 'account.group_account_invoice',
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
                summary=_("Currency Request Action Required"),
                note=_("Currency Request (%s) is awaiting your action (State: %s).") % (self.name, next_state)
            )

    def action_view_rfq(self):
        self.ensure_one()
        if not self.rfq_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Foreign RFQ'),
            'res_model': 'foreign.rfq',
            'view_mode': 'form',
            'res_id': self.rfq_id.id,
            'target': 'current',
        }


