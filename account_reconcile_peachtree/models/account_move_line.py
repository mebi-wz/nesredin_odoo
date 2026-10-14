# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_reconcile_row_manually(self):
        """
        Manually reconcile an outstanding unreconciled bank journal line.

        Strategy:
          - Create a bank statement line using the outstanding line's account as the
            counterpart (instead of the default suspense account).
            This creates: Bank Account (DEBIT/CREDIT) + Outstanding Account (CREDIT/DEBIT)
          - Then reconcile the two outstanding account lines together (same account).
          - This preserves the bank balance correctly.
        """
        self.ensure_one()

        if self.reconciled:
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        journal = self.journal_id
        if not journal or journal.type != 'bank':
            raise UserError(_("Manual reconciliation is only supported for Bank journals."))

        if not journal.default_account_id:
            raise UserError(_(
                "Please configure a default account on the bank journal '%s' first."
            ) % journal.name)

        amount = self.amount_residual
        if not amount:
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        # Create a bank statement line, but pass our outstanding account as the
        # counterpart so the move will have:
        #   - Bank account (asset_cash):  DEBIT/CREDIT amount
        #   - Outstanding account:        CREDIT/DEBIT amount  ← same account as self
        open_period = self.env['account.bank.reconciliation.period'].search([
            ('journal_id', '=', journal.id),
            ('state', '=', 'open')
        ], order='period_date asc', limit=1)
        clearing_date = fields.Date.today()
        if open_period:
            clearing_date = open_period.period_date

        st_line = self.env['account.bank.statement.line'].create({
            'journal_id': journal.id,
            'date': clearing_date,
            'payment_ref': _('Manual Reconciliation: %s') % (self.name or self.move_id.name or '/'),
            'partner_id': self.partner_id.id or False,
            # amount sign: positive = inbound (bank DEBIT + counterpart CREDIT)
            #              negative = outbound (bank CREDIT + counterpart DEBIT)
            # If the outstanding line is a CREDIT (residual < 0), the new counterpart must be
            # DEBIT to cancel it. A DEBIT counterpart is created when bank statement amount < 0
            # (outbound). So: amount = amount_residual (which is negative for a credit line).
            'amount': amount,
            # Override the suspense account with the outstanding account so both lines
            # share the same account and can be reconciled by reconcile().
            'counterpart_account_id': self.account_id.id,
        })

        # Find the counterpart line (on the same account as self) in the new bank statement move
        counterpart_line = st_line.move_id.line_ids.filtered(
            lambda l: l.account_id == self.account_id
        )

        if counterpart_line:
            (self | counterpart_line).reconcile()

        # Flush the environment so the computed 'reconciled' fields are saved to the database.
        # This ensures the subsequent search() query correctly excludes the reconciled lines.
        self.env.flush_all()
        self._refresh_open_reconciliations(journal)

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_unreconcile_row_manually(self):
        """
        Manually unreconcile a reconciled bank journal line.

        Strategy:
          - Find all related reconciled lines.
          - Find any generated bank statement lines linked to these reconciled lines.
          - Break the reconciliation relation.
          - Delete the generated bank statement lines to restore the bank balance and keep it clean.
        """
        self.ensure_one()

        target_line = self
        journal = self.journal_id
        if journal and self.account_id == journal.default_account_id:
            # If the user clicked on a bank account line (not outstanding), find the corresponding
            # outstanding counterpart line in the statement's move
            if self.statement_line_id:
                counterpart_lines = self.statement_line_id.move_id.line_ids.filtered(
                    lambda l: l.account_id != journal.default_account_id
                )
                reconciled_counterpart = counterpart_lines.filtered(lambda l: l.reconciled)
                if reconciled_counterpart:
                    target_line = reconciled_counterpart[0]
                elif counterpart_lines:
                    target_line = counterpart_lines[0]

        if not target_line.reconciled:
            if self.statement_line_id:
                self.statement_line_id.with_context(force_delete=True).unlink()
            return {'type': 'ir.actions.client', 'tag': 'reload'}

        # Get all reconciled lines matched with this one
        reconciled_lines = target_line._all_reconciled_lines()

        # Find any generated bank statement lines
        st_lines = reconciled_lines.mapped('statement_line_id')

        # Break the reconciliation
        reconciled_lines.remove_move_reconcile()

        # Delete the generated bank statement lines
        if st_lines:
            st_lines.with_context(force_delete=True).unlink()

        # Flush before refresh so SQL searches see the broken reconciliations
        self.env.flush_all()
        self._refresh_open_reconciliations(journal)

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_reconcile_bulk_manually(self):
        """
        Manually reconcile multiple selected outstanding unreconciled bank journal lines in bulk.
        """
        for record in self:
            if not record.reconciled:
                record.action_reconcile_row_manually()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_unreconcile_bulk_manually(self):
        """
        Manually unreconcile multiple selected reconciled bank journal lines in bulk.
        """
        for record in self:
            record.action_unreconcile_row_manually()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _refresh_open_reconciliations(self, journal):
        """Helper to update the saved lists on open reconciliations so the UI refreshes."""
        open_periods = self.env['account.bank.reconciliation.period'].search([
            ('journal_id', '=', journal.id),
            ('state', '=', 'open')
        ])
        for period in open_periods:
            # Re-fetch the lines from the DB
            accounts = journal._get_reconciliation_outstanding_accounts()
            out_domain = [
                ('journal_id', '=', journal.id),
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('statement_line_id', '=', False),
                ('date', '<=', period.period_date),
            ]
            out_lines = self.env['account.move.line'].search(out_domain)
            dep_ids = out_lines.filtered(lambda l: l.amount_residual > 0).ids
            chk_ids = out_lines.filtered(lambda l: l.amount_residual < 0).ids

            from dateutil.relativedelta import relativedelta
            month_start = period.period_date.replace(day=1)
            rec_domain = [
                ('journal_id', '=', journal.id),
                ('account_id', '=', journal.default_account_id.id),
                ('parent_state', '=', 'posted'),
                ('statement_line_id', '!=', False),
                ('date', '>=', month_start),
                ('date', '<=', period.period_date),
            ]
            rec_ids = self.env['account.move.line'].search(rec_domain).ids

            period.write({
                'outstanding_deposit_ids': [(6, 0, dep_ids)],
                'outstanding_check_ids': [(6, 0, chk_ids)],
                'reconciled_line_ids': [(6, 0, rec_ids)],
            })
            period._compute_balances()


