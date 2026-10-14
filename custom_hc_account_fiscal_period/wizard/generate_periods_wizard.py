from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GenerateFiscalPeriodsWizard(models.TransientModel):
    _name = 'account.fiscal.period.generate.wizard'
    _description = 'Generate Fiscal Periods'

    fiscal_year_id = fields.Many2one('account.fiscal.year', required=True)
    number_of_periods = fields.Integer(
        default=12, required=True,
        help="Must divide evenly into 12 (12, 6, 4, 3, 2 or 1).",
    )
    overwrite_existing = fields.Boolean(
        default=True, string='Replace existing periods',
        help="If checked, any periods already on this fiscal year are deleted first.",
    )
    period_names = fields.Text(
        string='Period Descriptions (optional, one per line)',
        help="Optional: one label per line, in order, e.g. your local calendar "
             "month names (Hamle 2018, Nehase 2018, Meskerem 2018, ...). "
             "Leave blank to leave Description empty.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and 'fiscal_year_id' in fields_list:
            res['fiscal_year_id'] = active_id
        return res

    def action_generate(self):
        self.ensure_one()
        year = self.fiscal_year_id
        if not year.date_from or not year.date_to:
            raise UserError(_('The fiscal year must have a Start Date and End Date first.'))
        if self.number_of_periods <= 0 or 12 % self.number_of_periods != 0:
            raise UserError(_('Number of periods must divide evenly into 12 '
                               '(e.g. 12, 6, 4, 3, 2 or 1).'))

        if self.overwrite_existing:
            year.period_ids.unlink()

        names = [n.strip() for n in (self.period_names or '').split('\n') if n.strip()]
        step_months = 12 // self.number_of_periods

        vals_list = []
        current_start = year.date_from
        for i in range(self.number_of_periods):
            if i == self.number_of_periods - 1:
                current_end = year.date_to
            else:
                current_end = current_start + relativedelta(months=step_months, days=-1)
            vals_list.append({
                'fiscal_year_id': year.id,
                'name': _('Period %s') % (i + 1),
                'code': 'P%02d' % (i + 1),
                'description': names[i] if i < len(names) else '',
                'date_from': current_start,
                'date_to': current_end,
            })
            current_start = current_end + relativedelta(days=1)

        self.env['account.fiscal.period'].create(vals_list)
        return {'type': 'ir.actions.act_window_close'}
