# -*- coding: utf-8 -*-
import calendar
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountBankReconciliationPeriod(models.Model):
    """Saved snapshot of a bank reconciliation for a specific period."""
    _name = 'account.bank.reconciliation.period'
    _description = 'Bank Reconciliation Period'
    _order = 'period_date desc, journal_id'
    _rec_name = 'name'

    name = fields.Char(
        string='Name', compute='_compute_name', store=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True,
        domain=[('type', '=', 'bank')], ondelete='restrict',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', compute='_compute_currency_id', store=True,
    )
    period_date = fields.Date(
        string='Statement Date', required=True,
        help='The bank statement closing date for this reconciliation period.',
    )
    statement_balance = fields.Monetary(
        string='Statement Ending Balance', required=True,
    )

    # ─── Saved balances (snapshot at time of saving) ──────────────────────────

    book_balance = fields.Monetary(
        string='Book Balance (GL)',
        compute='_compute_balances', store=True, readonly=False,
    )
    outstanding_deposits = fields.Monetary(
        string='Outstanding Deposits',
        compute='_compute_balances', store=True, readonly=False,
    )
    outstanding_checks = fields.Monetary(
        string='Outstanding Checks/Payments',
        compute='_compute_balances', store=True, readonly=False,
    )
    difference = fields.Monetary(
        string='Difference',
        compute='_compute_balances', store=True, readonly=False,
    )

    # ─── Status ───────────────────────────────────────────────────────────────

    state = fields.Selection([
        ('open', 'Open'),
        ('balanced', 'Balanced'),
        ('locked', 'Locked'),
    ], string='Status', default='open', required=True, tracking=True)

    notes = fields.Text(string='Notes')

    # ─── Line references ──────────────────────────────────────────────────────

    outstanding_deposit_ids = fields.Many2many(
        'account.move.line',
        'reconcile_period_deposit_rel', 'period_id', 'line_id',
        string='Outstanding Deposits',
        compute='_compute_lines', store=True, readonly=False,
    )
    outstanding_check_ids = fields.Many2many(
        'account.move.line',
        'reconcile_period_check_rel', 'period_id', 'line_id',
        string='Outstanding Checks/Payments',
        compute='_compute_lines', store=True, readonly=False,
    )
    reconciled_line_ids = fields.Many2many(
        'account.move.line',
        'reconcile_period_reconciled_rel', 'period_id', 'line_id',
        string='Reconciled Items',
        compute='_compute_lines', store=True, readonly=False,
    )

    _sql_constraints = [
        (
            'unique_journal_period',
            'UNIQUE(journal_id, period_date)',
            'A reconciliation record already exists for this journal and period date.',
        ),
    ]

    # ─── Computes ─────────────────────────────────────────────────────────────

    @api.depends('journal_id', 'period_date')
    def _compute_name(self):
        for rec in self:
            if rec.journal_id and rec.period_date:
                rec.name = '%s — %s' % (
                    rec.journal_id.name,
                    rec.period_date.strftime('%B %Y'),
                )
            else:
                rec.name = _('New Reconciliation')

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.company_id.currency_id

    @api.depends('journal_id', 'period_date')
    def _compute_lines(self):
        for rec in self:
            if rec.state in ('balanced', 'locked'):
                continue
            if not rec.journal_id or not rec.period_date:
                rec.outstanding_deposit_ids = False
                rec.outstanding_check_ids = False
                rec.reconciled_line_ids = False
                continue

            # 1. Outstanding lines
            accounts = rec.journal_id._get_reconciliation_outstanding_accounts()
            out_domain = [
                ('journal_id', '=', rec.journal_id.id),
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('statement_line_id', '=', False),
                ('date', '<=', rec.period_date),
            ]
            out_lines = self.env['account.move.line'].search(out_domain)
            rec.outstanding_deposit_ids = out_lines.filtered(lambda l: l.amount_residual > 0)
            rec.outstanding_check_ids = out_lines.filtered(lambda l: l.amount_residual < 0)

            # 2. Reconciled lines (cleared in this month)
            rec_domain = [
                ('journal_id', '=', rec.journal_id.id),
                ('account_id', '=', rec.journal_id.default_account_id.id),
                ('parent_state', '=', 'posted'),
                ('statement_line_id', '!=', False),
                ('date', '>=', date(rec.period_date.year, rec.period_date.month, 1)),
                ('date', '<=', rec.period_date),
            ]
            rec.reconciled_line_ids = self.env['account.move.line'].search(rec_domain)

    @api.depends('journal_id', 'period_date', 'statement_balance', 'outstanding_deposit_ids', 'outstanding_check_ids')
    def _compute_balances(self):
        for rec in self:
            if rec.state in ('balanced', 'locked'):
                continue
            if not rec.journal_id or not rec.period_date:
                rec.book_balance = 0.0
                rec.outstanding_deposits = 0.0
                rec.outstanding_checks = 0.0
                rec.difference = 0.0
                continue

            # Book Balance
            accounts = rec.journal_id.default_account_id | rec.journal_id._get_reconciliation_outstanding_accounts()
            book_domain = [
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
                ('date', '<=', rec.period_date),
            ]
            book_lines = self.env['account.move.line'].search(book_domain)
            book_bal = sum(book_lines.mapped(lambda l: l.debit - l.credit))

            # Outstanding sums
            out_dep = sum(l.amount_residual for l in rec.outstanding_deposit_ids)
            out_chk = sum(-l.amount_residual for l in rec.outstanding_check_ids)

            rec.book_balance = book_bal
            rec.outstanding_deposits = out_dep
            rec.outstanding_checks = out_chk
            rec.difference = (rec.statement_balance + out_dep - out_chk) - book_bal

    # ─── Computed display helpers ─────────────────────────────────────────────

    is_balanced = fields.Boolean(
        string='Balanced', compute='_compute_is_balanced', store=True,
    )

    @api.depends('difference')
    def _compute_is_balanced(self):
        for rec in self:
            rec.is_balanced = rec.difference == 0.0

    # ─── Actions ──────────────────────────────────────────────────────────────

    def action_set_balanced(self):
        for rec in self:
            if rec.difference != 0.0:
                raise UserError(_(
                    'Cannot mark as Balanced: difference is %.2f. '
                    'Please reconcile all outstanding items first.'
                ) % rec.difference)
            rec.state = 'balanced'

    def action_lock(self):
        for rec in self:
            if rec.state != 'balanced':
                raise UserError(_('Only balanced reconciliations can be locked.'))
            rec.state = 'locked'

    def action_reopen(self):
        for rec in self:
            if rec.state == 'locked':
                raise UserError(_(
                    'This reconciliation is locked and cannot be reopened. '
                    'Contact your administrator.'
                ))
            rec.state = 'open'

    @api.constrains('journal_id', 'period_date')
    def _check_chronology(self):
        for rec in self:
            other = self.search([
                ('journal_id', '=', rec.journal_id.id),
                ('id', '!=', rec.id),
            ])
            if not other:
                continue

            # 1. Only one period per month
            rec_month = (rec.period_date.year, rec.period_date.month)
            for o in other:
                if (o.period_date.year, o.period_date.month) == rec_month:
                    raise UserError(_(
                        "A reconciliation period already exists for %s. "
                        "Only one reconciliation period is allowed per month."
                    ) % rec.period_date.strftime('%B %Y'))

            # 2. Chronological order
            max_date = max(other.mapped('period_date'))
            is_new = not rec._origin.id
            date_changed = rec.period_date != rec._origin.period_date
            if (is_new or date_changed) and rec.period_date < max_date:
                raise UserError(_(
                    "The reconciliation date (%s) must be after the last "
                    "reconciliation period date (%s)."
                ) % (rec.period_date, max_date))

    @api.model
    def cron_auto_generate_reconciliations(self):
        """
        Scheduled action to automatically generate draft bank reconciliations
        when a fiscal period ends.
        """
        today = fields.Date.today()
        # Find periods that have already ended
        ended_periods = self.env['account.fiscal.period'].search([('date_to', '<', today)])
        if not ended_periods:
            return

        bank_journals = self.env['account.journal'].search([('type', '=', 'bank')])
        if not bank_journals:
            return

        for period in ended_periods:
            from dateutil.relativedelta import relativedelta
            month_start = period.date_to.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)
            
            for journal in bank_journals:
                existing = self.search([
                    ('journal_id', '=', journal.id),
                    ('period_date', '>=', month_start),
                    ('period_date', '<=', month_end),
                ], limit=1)
                
                if not existing:
                    # 1. Outstanding lines
                    accounts = journal._get_reconciliation_outstanding_accounts()
                    out_domain = [
                        ('journal_id', '=', journal.id),
                        ('account_id', 'in', accounts.ids),
                        ('parent_state', '=', 'posted'),
                        ('reconciled', '=', False),
                        ('statement_line_id', '=', False),
                        ('date', '<=', period.date_to),
                    ]
                    out_lines = self.env['account.move.line'].search(out_domain)
                    dep_ids = out_lines.filtered(lambda l: l.amount_residual > 0).ids
                    chk_ids = out_lines.filtered(lambda l: l.amount_residual < 0).ids

                    # 2. Reconciled lines
                    rec_domain = [
                        ('journal_id', '=', journal.id),
                        ('account_id', '=', journal.default_account_id.id),
                        ('parent_state', '=', 'posted'),
                        ('statement_line_id', '!=', False),
                        ('date', '>=', month_start),
                        ('date', '<=', period.date_to),
                    ]
                    rec_ids = self.env['account.move.line'].search(rec_domain).ids

                    # Create the draft snapshot and explicitly save the lists
                    draft_rec = self.create({
                        'journal_id': journal.id,
                        'company_id': journal.company_id.id,
                        'period_date': period.date_to,
                        'statement_balance': 0.0,
                        'state': 'open',
                        'outstanding_deposit_ids': [(6, 0, dep_ids)],
                        'outstanding_check_ids': [(6, 0, chk_ids)],
                        'reconciled_line_ids': [(6, 0, rec_ids)],
                    })
                    # Recompute balances based on the saved lists
                    draft_rec._compute_balances()

