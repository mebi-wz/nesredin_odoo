from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_fiscal_period(self, date):
        return self.env['account.fiscal.period']._find_period_for_date(date, self.company_id)

    def _check_period_not_closed(self, date):
        period = self._get_fiscal_period(date)
        if period and period.state == 'closed':
            raise UserError(_(
                'You cannot post, edit or reset this entry.\n'
                'Its date (%(date)s) falls inside the closed period "%(period)s" '
                '(%(date_from)s to %(date_to)s). Ask an Accounting Manager to '
                're-open the period first if this change is really needed.'
            ) % {
                'date': date,
                'period': period.name,
                'date_from': period.date_from,
                'date_to': period.date_to,
            })

    def _post(self, soft=True):
        for move in self:
            move._check_period_not_closed(move.date)
        return super()._post(soft=soft)

    def button_draft(self):
        for move in self:
            if move.state == 'posted':
                move._check_period_not_closed(move.date)
        return super().button_draft()

    def write(self, vals):
        # Only bother checking when something financially meaningful changes
        # on an already-posted entry.
        sensitive_fields = {'date', 'line_ids', 'journal_id', 'amount_total'}
        if sensitive_fields.intersection(vals.keys()):
            for move in self:
                if move.state == 'posted':
                    check_date = vals.get('date', move.date)
                    move._check_period_not_closed(check_date)
        return super().write(vals)
