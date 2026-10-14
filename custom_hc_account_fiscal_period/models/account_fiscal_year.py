from odoo import fields, models


class AccountFiscalYear(models.Model):
    _inherit = 'account.fiscal.year'

    period_ids = fields.One2many(
        'account.fiscal.period', 'fiscal_year_id', string='Periods', copy=True,
    )
    period_count = fields.Integer(compute='_compute_period_count')
    period_status = fields.Selection(
        [
            ('none', 'No Periods'),
            ('draft', 'Not Started'),
            ('mixed', 'Partially Closed'),
            ('open', 'All Open'),
            ('closed', 'Fully Closed'),
        ],
        string='Periods Status', compute='_compute_period_count',
        help="Quick summary of period states for this fiscal year, shown in the list view.",
    )

    def _compute_period_count(self):
        for year in self:
            periods = year.period_ids
            year.period_count = len(periods)
            states = set(periods.mapped('state'))
            if not states:
                year.period_status = 'none'
            elif states == {'closed'}:
                year.period_status = 'closed'
            elif states == {'draft'}:
                year.period_status = 'draft'
            elif states == {'open'}:
                year.period_status = 'open'
            else:
                year.period_status = 'mixed'
