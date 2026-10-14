from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError


class AccountFiscalPeriod(models.Model):
    _name = 'account.fiscal.period'
    _inherit = ['mail.thread']
    _description = 'Fiscal Period'
    _order = 'date_from'

    name = fields.Char(string='Period', required=True, tracking=True)
    code = fields.Char(string='Code')
    description = fields.Char(
        string='Description',
        help="Local calendar label, e.g. an Ethiopian month name "
             "(Hamle 2018, Nehase 2018, Meskerem 2018, ...).",
    )
    date_from = fields.Date(string='Date From', required=True, tracking=True)
    date_to = fields.Date(string='Date To', required=True, tracking=True)
    fiscal_year_id = fields.Many2one(
        'account.fiscal.year', string='Fiscal Year',
        required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        related='fiscal_year_id.company_id', store=True, readonly=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('open', 'Open'),
            ('closed', 'Closed'),
        ],
        string='Status', default='draft', required=True, copy=False, tracking=True,
        help="Draft: not yet in use.\n"
             "Open: normal posting allowed.\n"
             "Closed: no journal entry, and no stock move, dated inside this "
             "period can be posted, validated, edited, or reset to draft.",
    )

    _sql_constraints = [
        ('code_year_uniq', 'unique(fiscal_year_id, code)',
         'Period code must be unique within a fiscal year.'),
    ]

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for period in self:
            if period.date_from and period.date_to and period.date_from > period.date_to:
                raise ValidationError(
                    _('The start date of period "%s" must be before its end date.') % period.name
                )

    @api.constrains('date_from', 'date_to', 'fiscal_year_id')
    def _check_overlap(self):
        for period in self:
            domain = [
                ('id', '!=', period.id),
                ('fiscal_year_id', '=', period.fiscal_year_id.id),
                ('date_from', '<=', period.date_to),
                ('date_to', '>=', period.date_from),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('Period "%s" overlaps with another period in the same fiscal year.') % period.name
                )

    def _require_period_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only Accounting Managers can change a period\'s status.'))

    def action_open(self):
        self._require_period_manager()
        self.write({'state': 'open'})
        for period in self:
            period.message_post(body=_('Period opened by %s.') % self.env.user.name)

    def action_close(self):
        self._require_period_manager()
        self.write({'state': 'closed'})
        for period in self:
            period.message_post(body=_('Period closed by %s. Journal entries and stock '
                                        'moves dated in this range are now locked.') % self.env.user.name)

    def action_reopen(self):
        self._require_period_manager()
        self.write({'state': 'draft'})
        for period in self:
            period.message_post(body=_('Period reopened by %s. Remember to Close it again '
                                        'once corrections are done.') % self.env.user.name)

    @api.model
    def _find_period_for_date(self, date, company):
        """Return the period (if any) that a given date falls into for a company."""
        if not date or not company:
            return self.browse()
        return self.search([
            ('company_id', '=', company.id),
            ('date_from', '<=', date),
            ('date_to', '>=', date),
        ], limit=1)
