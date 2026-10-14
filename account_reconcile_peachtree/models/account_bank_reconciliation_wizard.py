# -*- coding: utf-8 -*-
import calendar
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountBankReconciliationWizard(models.TransientModel):
    _name = 'account.bank.reconciliation.wizard'
    _description = 'Bank Reconciliation Wizard'

    # ─── Filter / Header fields ────────────────────────────────────────────────

    journal_id = fields.Many2one(
        'account.journal', string='Bank Journal', required=True,
        domain=[('type', '=', 'bank')],
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        compute='_compute_currency_id',
    )
    # Optional period filter – when blank, ALL items are shown
    statement_date = fields.Date(
        string='Statement Date',
        help='Filter items up to and including this date. Leave empty to see all items.',
    )
    statement_balance = fields.Monetary(
        string='Statement Ending Balance', default=0.0,
        help='The closing balance on the bank statement for this period.',
    )

    # ─── Computed summary ─────────────────────────────────────────────────────

    book_balance = fields.Monetary(
        string='Book Balance (GL)', compute='_compute_balances',
    )
    outstanding_deposits = fields.Monetary(
        string='Outstanding Deposits', compute='_compute_balances',
    )
    outstanding_checks = fields.Monetary(
        string='Outstanding Checks/Payments', compute='_compute_balances',
    )
    difference = fields.Monetary(
        string='Difference', compute='_compute_balances',
    )

    # ─── Line sets ────────────────────────────────────────────────────────────

    outstanding_deposit_ids = fields.Many2many(
        'account.move.line', compute='_compute_outstanding_lines',
        relation='reconcile_wiz_deposit_rel',
        string='Outstanding Deposits',
    )
    outstanding_check_ids = fields.Many2many(
        'account.move.line', compute='_compute_outstanding_lines',
        relation='reconcile_wiz_check_rel',
        string='Outstanding Checks/Payments',
    )
    reconciled_line_ids = fields.Many2many(
        'account.move.line', compute='_compute_reconciled_lines',
        relation='reconcile_wiz_reconciled_rel',
        string='Reconciled Items',
    )

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.company_id.currency_id

    def _period_end_date(self):
        """End of the month of statement_date, or None if no date set."""
        if not self.statement_date:
            return None
        d = self.statement_date
        _, last_day = calendar.monthrange(d.year, d.month)
        return date(d.year, d.month, last_day)

    def _outstanding_domain(self):
        """Domain for unreconciled transit lines, optionally filtered by date."""
        accounts = self.journal_id._get_reconciliation_outstanding_accounts()
        domain = [
            ('journal_id', '=', self.journal_id.id),
            ('account_id', 'in', accounts.ids),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('statement_line_id', '=', False),
        ]
        end = self._period_end_date()
        if end:
            domain.append(('date', '<=', end))
        return domain

    # ─── Compute methods ──────────────────────────────────────────────────────

    @api.depends('journal_id', 'statement_date', 'statement_balance')
    def _compute_balances(self):
        for rec in self:
            if not rec.journal_id:
                rec.book_balance = rec.outstanding_deposits = 0.0
                rec.outstanding_checks = rec.adjusted_bank_balance = 0.0
                rec.difference = 0.0
                continue

            end = rec._period_end_date()

            # Book Balance — all posted lines on the bank account and outstanding accounts up to end_date (or all time)
            accounts = rec.journal_id.default_account_id | rec.journal_id._get_reconciliation_outstanding_accounts()
            book_domain = [
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
            ]
            if end:
                book_domain.append(('date', '<=', end))
            book_lines = self.env['account.move.line'].search(book_domain)
            book_bal = sum(book_lines.mapped(lambda l: l.debit - l.credit))

            # Outstanding items
            out_lines = self.env['account.move.line'].search(rec._outstanding_domain())
            out_dep  = sum(l.amount_residual for l in out_lines if l.amount_residual > 0)
            out_chk  = sum(-l.amount_residual for l in out_lines if l.amount_residual < 0)

            rec.book_balance          = book_bal
            rec.outstanding_deposits  = out_dep
            rec.outstanding_checks    = out_chk
            rec.difference            = (rec.statement_balance + out_dep - out_chk) - book_bal

    @api.depends('journal_id', 'statement_date')
    def _compute_outstanding_lines(self):
        for rec in self:
            if not rec.journal_id:
                rec.outstanding_deposit_ids = False
                rec.outstanding_check_ids   = False
                continue
            out_lines = self.env['account.move.line'].search(rec._outstanding_domain())
            rec.outstanding_deposit_ids = out_lines.filtered(lambda l: l.amount_residual > 0)
            rec.outstanding_check_ids   = out_lines.filtered(lambda l: l.amount_residual < 0)

    @api.depends('journal_id', 'statement_date')
    def _compute_reconciled_lines(self):
        for rec in self:
            if not rec.journal_id:
                rec.reconciled_line_ids = False
                continue
            domain = [
                ('journal_id', '=', rec.journal_id.id),
                ('account_id', '=', rec.journal_id.default_account_id.id),
                ('parent_state', '=', 'posted'),
                ('statement_line_id', '!=', False),
            ]
            end = rec._period_end_date()
            if end:
                d = rec.statement_date
                domain += [
                    ('date', '>=', date(d.year, d.month, 1)),
                    ('date', '<=', end),
                ]
            rec.reconciled_line_ids = self.env['account.move.line'].search(domain)

    # ─── Save action ──────────────────────────────────────────────────────────

    def action_save_period(self):
        """Save the current reconciliation snapshot to a persistent period record."""
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_('Please select a bank journal before saving.'))
        if not self.statement_date:
            raise UserError(_('Please set a Statement Date before saving.'))

        Period = self.env['account.bank.reconciliation.period']

        # Use the last day of the selected month as the canonical period_date
        end = self._period_end_date()

        # Find existing record for this journal + period (upsert)
        existing = Period.search([
            ('journal_id', '=', self.journal_id.id),
            ('period_date', '=', end),
        ], limit=1)

        # Check chronology for new period
        if not existing:
            other = Period.search([
                ('journal_id', '=', self.journal_id.id),
            ])
            if other:
                max_date = max(other.mapped('period_date'))
                if end < max_date:
                    raise UserError(_(
                        "The reconciliation date (%s) must be after the last "
                        "reconciliation period date (%s)."
                    ) % (end, max_date))

        vals = {
            'journal_id':           self.journal_id.id,
            'company_id':           self.company_id.id,
            'period_date':          end,
            'statement_balance':    self.statement_balance,
            'book_balance':         self.book_balance,
            'outstanding_deposits': self.outstanding_deposits,
            'outstanding_checks':   self.outstanding_checks,
            'difference':           self.difference,
            'outstanding_deposit_ids': [(6, 0, self.outstanding_deposit_ids.ids)],
            'outstanding_check_ids':   [(6, 0, self.outstanding_check_ids.ids)],
            'reconciled_line_ids':     [(6, 0, self.reconciled_line_ids.ids)],
        }

        if existing and existing.state == 'locked':
            raise UserError(_(
                'The reconciliation for %s is locked and cannot be overwritten.'
            ) % existing.name)

        if existing:
            existing.write(vals)
            period = existing
        else:
            period = Period.create(vals)

        # Navigate to the saved period record
        return {
            'name': period.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.bank.reconciliation.period',
            'view_mode': 'form',
            'res_id': period.id,
            'target': 'current',
        }

