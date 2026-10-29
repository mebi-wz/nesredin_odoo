# -*- coding: utf-8 -*-
import datetime
import calendar
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleTopBuyersAnalysis(models.TransientModel):
    _name = 'sale.top.buyers.analysis'
    _description = 'Top N Buyers Analysis & Ranking'

    limit_n = fields.Integer(
        string='Top N Buyers',
        required=True,
        default=lambda self: self.env.company.top_buyers_limit_n or 10,
        help="Number of top buyers to display (e.g. 5, 10, 20)."
    )
    metric = fields.Selection([
        ('value', 'Sales Value (Untaxed Subtotal)'),
        ('volume', 'Sales Volume (Total Units)'),
        ('revenue', 'Revenue (Gross Total)'),
    ], string='Ranking Metric', required=True, default=lambda self: self.env.company.top_buyers_default_metric or 'value',
       help="Metric used to rank buyers: Volume (Units), Value (Untaxed), or Revenue (Gross).")

    period = fields.Selection([
        ('this_month', 'This Month'),
        ('this_quarter', 'This Quarter'),
        ('this_year', 'This Year'),
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('custom', 'Custom Date Range'),
    ], string='Period', required=True, default=lambda self: self.env.company.top_buyers_default_period or 'this_month')

    date_from = fields.Date(string='Start Date', required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='End Date', required=True, default=fields.Date.context_today)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )

    line_ids = fields.One2many(
        'sale.top.buyers.line',
        'analysis_id',
        string='Top Buyers Ranking'
    )

    # Executive KPI Summary Cards
    total_company_sales = fields.Monetary(
        string='Total Company Sales in Period',
        currency_field='currency_id',
        readonly=True
    )
    total_top_buyers_sales = fields.Monetary(
        string='Top N Buyers Total Sales',
        currency_field='currency_id',
        readonly=True
    )
    top_buyers_share = fields.Float(
        string='Top N Share of Total (%)',
        readonly=True
    )
    total_top_buyers_units = fields.Float(
        string='Top N Units Sold',
        readonly=True
    )

    @api.constrains('limit_n')
    def _check_limit_n(self):
        for rec in self:
            if rec.limit_n < 1:
                raise ValidationError(_("The number of buyers (N) must be at least 1."))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("Start Date cannot be after End Date."))

    @api.onchange('period')
    def _onchange_period(self):
        today = fields.Date.context_today(self)
        if self.period == 'today':
            self.date_from = today
            self.date_to = today
        elif self.period == 'this_week':
            self.date_from = today - datetime.timedelta(days=today.weekday())
            self.date_to = self.date_from + datetime.timedelta(days=6)
        elif self.period == 'this_month':
            self.date_from = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            self.date_to = today.replace(day=last_day)
        elif self.period == 'this_quarter':
            quarter_start_month = 3 * ((today.month - 1) // 3) + 1
            self.date_from = today.replace(month=quarter_start_month, day=1)
            quarter_end_month = quarter_start_month + 2
            _, last_day = calendar.monthrange(today.year, quarter_end_month)
            self.date_to = today.replace(month=quarter_end_month, day=last_day)
        elif self.period == 'this_year':
            self.date_from = today.replace(month=1, day=1)
            self.date_to = today.replace(month=12, day=31)

    def action_compute_ranking(self):
        """Computes Top N Buyers according to chosen parameters (NSP-12.4)."""
        self.ensure_one()
        dt_start = datetime.datetime.combine(self.date_from, datetime.time.min)
        dt_end = datetime.datetime.combine(self.date_to, datetime.time.max)

        # Base domain for confirmed orders
        domain = [
            ('date_order', '>=', dt_start),
            ('date_order', '<=', dt_end),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ('sale', 'done')),
        ]

        orders = self.env['sale.order'].search(domain)
        order_lines = orders.mapped('order_line').filtered(lambda l: not l.display_type)

        # 1. Total Company Sales in Period (for % concentration calculation)
        total_period_value = sum(orders.mapped('amount_untaxed'))
        total_period_revenue = sum(orders.mapped('amount_total'))
        total_period_volume = sum(order_lines.mapped('product_uom_qty'))

        # 2. Aggregate by Customer (partner_id)
        buyer_data = {}
        for order in orders:
            buyer = order.partner_id
            if buyer.id not in buyer_data:
                buyer_data[buyer.id] = {
                    'partner': buyer,
                    'order_ids': set(),
                    'volume': 0.0,
                    'value': 0.0,
                    'revenue': 0.0,
                }
            entry = buyer_data[buyer.id]
            entry['order_ids'].add(order.id)
            entry['value'] += order.amount_untaxed
            entry['revenue'] += order.amount_total

        # Sum line volumes by partner
        for line in order_lines:
            buyer_id = line.order_id.partner_id.id
            if buyer_id in buyer_data:
                buyer_data[buyer_id]['volume'] += line.product_uom_qty

        # 3. Sort by Selected Metric (with tie handling)
        metric_key = self.metric  # 'value', 'volume', or 'revenue'
        sorted_buyers = sorted(
            buyer_data.values(),
            key=lambda x: (x[metric_key], x['revenue'], x['value']),
            reverse=True
        )

        # Take Top N
        top_n_buyers = sorted_buyers[:self.limit_n]

        # 4. Create line records with Rank and Ties handling
        lines_vals = []
        current_rank = 1
        previous_metric_val = None

        top_val_sum = 0.0
        top_vol_sum = 0.0

        for i, b in enumerate(top_n_buyers):
            val = b[metric_key]
            # If tie, share the same rank; otherwise rank is index + 1
            if previous_metric_val is not None and val == previous_metric_val:
                rank_assigned = current_rank
            else:
                rank_assigned = i + 1
                current_rank = rank_assigned
            previous_metric_val = val

            # Calculate % share of total company sales in this period
            base_total = total_period_revenue if self.metric == 'revenue' else (total_period_volume if self.metric == 'volume' else total_period_value)
            share = (val / base_total * 100.0) if base_total > 0 else 0.0

            top_val_sum += b['value']
            top_vol_sum += b['volume']

            lines_vals.append((0, 0, {
                'rank': rank_assigned,
                'partner_id': b['partner'].id,
                'order_count': len(b['order_ids']),
                'total_units': b['volume'],
                'sales_value': b['value'],
                'revenue': b['revenue'],
                'metric_value': val,
                'share_percentage': round(share, 2),
                'currency_id': self.currency_id.id,
            }))

        # Reopen self with populated lines and KPIs
        base_company_total = total_period_revenue if self.metric == 'revenue' else total_period_value
        overall_share = (top_val_sum / base_company_total * 100.0) if base_company_total > 0 else 0.0

        self.line_ids.unlink()
        self.write({
            'line_ids': lines_vals,
            'total_company_sales': base_company_total,
            'total_top_buyers_sales': top_val_sum,
            'top_buyers_share': round(overall_share, 1),
            'total_top_buyers_units': top_vol_sum,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.top.buyers.analysis',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_pdf(self):
        """Generates and downloads the executive Top N Buyers PDF report."""
        self.ensure_one()
        # Compute if not computed yet
        if not self.line_ids:
            self.action_compute_ranking()
        return self.env.ref('ibms_sale.action_report_sale_top_buyers').report_action(self)


class SaleTopBuyersLine(models.TransientModel):
    _name = 'sale.top.buyers.line'
    _description = 'Top Buyers Analysis Line'
    _order = 'rank asc, id asc'

    analysis_id = fields.Many2one('sale.top.buyers.analysis', ondelete='cascade', required=True)
    rank = fields.Integer(string='Rank', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Buyer / Customer', readonly=True)
    partner_ref = fields.Char(string='Customer Code', related='partner_id.ref', readonly=True)
    order_count = fields.Integer(string='Orders', readonly=True)
    total_units = fields.Float(string='Volume (Units)', readonly=True)
    sales_value = fields.Monetary(string='Sales Value (Untaxed)', currency_field='currency_id', readonly=True)
    revenue = fields.Monetary(string='Revenue (Gross)', currency_field='currency_id', readonly=True)
    metric_value = fields.Float(string='Rank Metric Value', readonly=True)
    share_percentage = fields.Float(string='% Share', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
