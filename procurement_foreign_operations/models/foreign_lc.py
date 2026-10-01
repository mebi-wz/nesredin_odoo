from odoo import models, fields, api, _
from datetime import timedelta


class ForeignLC(models.Model):
    _name = 'foreign.lc'
    _description = 'Letter of Credit'
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
        related='purchase_order_id.partner_id',
        store=True,
        readonly=True
    )

    # LC Details
    instrument_type = fields.Selection([
        ('lc', 'Letter of Credit (LC)'),
        ('tt', 'Telegraphic Transfer (TT)'),
        ('cad', 'Cash Against Documents (CAD)'),
    ], string="Instrument Type", default='lc', required=True, tracking=True)
    lc_number = fields.Char(string="LC Number", required=True, tracking=True)
    lc_type = fields.Selection([
        ('sight', 'At Sight'),
        ('usance', 'Usance'),
        ('standby', 'Standby'),
        ('revolving', 'Revolving'),
    ], string="LC Type", tracking=True)

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='purchase_order_id.currency_id',
        store=True,
        readonly=True,
    )
    amount = fields.Float(string="LC Amount", required=True, tracking=True)

    # Banks
    issuing_bank = fields.Many2one('res.bank', string="Bank", tracking=True)
    bank_branch = fields.Char(string="Branch", tracking=True)
    advising_bank = fields.Many2one('res.bank', string="Advising Bank", tracking=True)

    # Dates
    issue_date = fields.Date(string="Issue Date", tracking=True)
    start_date = fields.Date(string="Start Date", tracking=True)
    expiry_date = fields.Date(string="Expire Date", tracking=True)
    last_shipment_date = fields.Date(string="Last Day of Shipment", tracking=True)
    request_approved_date = fields.Date(string="Request Approved Date", tracking=True)

    # Approved Dates
    draft_lc_approved_date = fields.Date(string="Draft LC Approved Date", tracking=True)
    draft_lc_approved_date_supplier = fields.Date(string="Draft LC Approved Date by Supplier", tracking=True)
    lc_send_date_supplier = fields.Date(string="LC Send Date to Supplier", tracking=True)
    lc_received_date_bank = fields.Date(string="LC Recived Date from Bank", tracking=True)

    # Financial - pulled from Purchase Order
    total_amount_usd = fields.Monetary(
        string="Total Amount USD/Others",
        related='purchase_order_id.amount_total',
        currency_field='currency_id',
        store=True,
        readonly=True,
    )
    exchange_rate = fields.Float(
        string="Exchange Rate",
        related='purchase_order_id.exchange_rate',
        digits=(16, 4),
        store=True,
        readonly=True,
    )
    total_amount_etb = fields.Float(string="Total Amount ETB", compute='_compute_total_etb', store=True, tracking=True)

    # Status
    days_to_expiry = fields.Integer(string="Days to Expiry", compute='_compute_days_to_expiry')
    is_expired = fields.Boolean(string="Expired", compute='_compute_days_to_expiry')
    is_near_expiry = fields.Boolean(string="Near Expiry", compute='_compute_days_to_expiry')
    lc_alert_days = fields.Integer(string="Alert Days", compute='_compute_lc_alert_days')


    # Additional
    tolerance_percentage = fields.Float(string="Tolerance (%)", tracking=True)
    remarks = fields.Text(string="Remarks", tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('active', 'Active'),
        ('amended', 'Amended'),
        ('expired', 'Expired'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    amendment_ids = fields.One2many('foreign.lc.amendment', 'lc_id', string='Amendments')
    amendment_count = fields.Integer(compute='_compute_amendment_count')
    draft_reconciliation_ids = fields.One2many('foreign.lc.draft.reconciliation', 'lc_id', string='LC Draft Reconciliation')

    attachment_ids = fields.Many2many(
        'ir.attachment', 'lc_attachment_rel',
        string='Attachments'
    )

    @api.depends('amendment_ids')
    def _compute_amendment_count(self):
        for rec in self:
            rec.amendment_count = len(rec.amendment_ids)

    @api.depends('total_amount_usd', 'exchange_rate')
    def _compute_total_etb(self):
        for rec in self:
            rec.total_amount_etb = rec.total_amount_usd * rec.exchange_rate

    def _compute_lc_alert_days(self):
        for rec in self:
            rec.lc_alert_days = rec.company_id.lc_alert_days or 30

    @api.depends('expiry_date')
    def _compute_days_to_expiry(self):
        today = fields.Date.today()
        for rec in self:
            if rec.expiry_date:
                rec.days_to_expiry = (rec.expiry_date - today).days
                rec.is_expired = rec.days_to_expiry < 0
                alert_days = rec.company_id.lc_alert_days or 30
                rec.is_near_expiry = 0 <= rec.days_to_expiry <= alert_days
            else:
                rec.days_to_expiry = 0
                rec.is_expired = False
                rec.is_near_expiry = False

    @api.onchange('issue_date')
    def _onchange_issue_date(self):
        if self.issue_date:
            lc_expiry_days = self.company_id.lc_expiry_days or 180
            self.expiry_date = self.issue_date + timedelta(days=lc_expiry_days)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('foreign.lc') or _('New')
        return super().create(vals_list)

    def action_issue(self):
        self.write({'state': 'issued'})

    def action_activate(self):
        self.write({'state': 'active', 'start_date': fields.Date.today()})

    def action_amend(self):
        self.write({'state': 'amended'})

    def action_expire(self):
        self.write({'state': 'expired'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})


class ForeignLCAmendment(models.Model):
    _name = 'foreign.lc.amendment'
    _description = 'LC Amendment'
    _order = 'amendment_date desc'

    lc_id = fields.Many2one('foreign.lc', string='LC', required=True, ondelete='cascade')
    amendment_no = fields.Char(string="Amendment No", required=True)
    amendment_date = fields.Date(string="Amendment Date", default=fields.Date.context_today)
    description = fields.Text(string="Description")
    new_amount = fields.Float(string="New Amount")
    new_expiry_date = fields.Date(string="New Expiry Date")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='lc_id.company_id',
        store=True,
        readonly=True
    )


class ForeignLCDraftReconciliation(models.Model):
    _name = 'foreign.lc.draft.reconciliation'
    _description = 'LC Draft Reconciliation'
    _order = 'step_order'

    lc_id = fields.Many2one('foreign.lc', string='LC', required=True, ondelete='cascade')
    step_order = fields.Integer(string="Step Order", default=1)
    name = fields.Char(string="Name", required=True)
    state = fields.Selection([
        ('right', 'Right'),
        ('wrong', 'Wrong'),
    ], string="State", default='right')
    remark = fields.Text(string="Remark")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='lc_id.company_id',
        store=True,
        readonly=True
    )
