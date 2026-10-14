from odoo import fields, models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _check_period_not_closed(self, move_date):
        check_date = fields.Date.to_date(move_date)
        period = self.env['account.fiscal.period']._find_period_for_date(check_date, self.company_id)
        if period and period.state == 'closed':
            raise UserError(_(
                'You cannot validate this stock move.\n'
                'Its date (%(date)s) falls inside the closed period "%(period)s" '
                '(%(date_from)s to %(date_to)s).\n'
                'An Accounting Manager must re-open the period first if this '
                'correction is genuinely needed, then close it again once done.'
            ) % {
                'date': check_date,
                'period': period.name,
                'date_from': period.date_from,
                'date_to': period.date_to,
            })

    def _action_done(self, cancel_backorder=False):
        for move in self:
            move._check_period_not_closed(move.date)
        return super()._action_done(cancel_backorder=cancel_backorder)
