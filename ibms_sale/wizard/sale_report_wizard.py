# -*- coding: utf-8 -*-
from datetime import datetime, time
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleReportWizard(models.TransientModel):
    _name = 'sale.report.wizard'
    _description = 'Sales Report Wizard (Daily, Customer, Product)'

    report_type = fields.Selection([
        ('daily', 'Daily Sales Report'),
        ('customer', 'Sales Report per Customer'),
        ('product', 'Sales Report per Product'),
        ('all', 'Comprehensive Sales Summary'),
    ], string='Report Type', default='daily', required=True)

    date_from = fields.Date(
        string='Start Date',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        default=fields.Date.context_today,
    )

    partner_ids = fields.Many2many(
        'res.partner',
        string='Customers',
        help="Leave blank to include all customers.",
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        help="Leave blank to include all products.",
    )
    order_state = fields.Selection([
        ('confirmed', 'Confirmed Sales Orders Only'),
        ('all', 'All Quotations and Orders'),
    ], string='Order Status', default='confirmed', required=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("Start Date cannot be later than End Date!"))

    def action_view_on_screen(self):
        """Opens interactive analytical view corresponding to selected report type."""
        self.ensure_one()
        dt_start = datetime.combine(self.date_from, time.min)
        dt_end = datetime.combine(self.date_to, time.max)

        domain = [
            ('date', '>=', dt_start),
            ('date', '<=', dt_end),
            ('company_id', '=', self.company_id.id),
        ]
        if self.order_state == 'confirmed':
            domain.append(('state', 'not in', ('draft', 'cancel', 'sent')))

        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))

        if self.report_type == 'daily':
            action = self.env['ir.actions.act_window']._for_xml_id('ibms_sale.action_sale_report_daily')
            action['domain'] = domain
            action['context'] = {
                'search_default_group_by_day': 1,
            }
            return action

        elif self.report_type == 'customer':
            action = self.env['ir.actions.act_window']._for_xml_id('ibms_sale.action_sale_report_customer')
            action['domain'] = domain
            action['context'] = {
                'search_default_Customer': 1,
            }
            return action

        elif self.report_type == 'product':
            action = self.env['ir.actions.act_window']._for_xml_id('ibms_sale.action_sale_report_product')
            action['domain'] = domain
            action['context'] = {
                'search_default_Product': 1,
            }
            return action

        else:
            action = self.env['ir.actions.act_window']._for_xml_id('sale.action_order_report_all')
            action['domain'] = domain
            return action

    def action_print_pdf(self):
        """Generates and prints professional QWeb PDF sales report."""
        self.ensure_one()
        return self.env.ref('ibms_sale.action_report_custom_sales').report_action(self)

    def _get_report_data(self):
        """Prepares structured data for PDF QWeb report template."""
        self.ensure_one()
        dt_start = datetime.combine(self.date_from, time.min)
        dt_end = datetime.combine(self.date_to, time.max)

        order_domain = [
            ('date_order', '>=', dt_start),
            ('date_order', '<=', dt_end),
            ('company_id', '=', self.company_id.id),
        ]
        if self.order_state == 'confirmed':
            order_domain.append(('state', 'in', ('sale', 'done')))
        else:
            order_domain.append(('state', '!=', 'cancel'))

        if self.partner_ids:
            order_domain.append(('partner_id', 'in', self.partner_ids.ids))

        orders = self.env['sale.order'].search(order_domain, order='date_order asc')

        lines = orders.order_line.filtered(
            lambda l: not l.display_type and l.product_id
        )
        if self.product_ids:
            lines = lines.filtered(lambda l: l.product_id in self.product_ids)

        total_orders = len(orders)
        total_amount = sum(orders.mapped('amount_total'))
        total_untaxed = sum(orders.mapped('amount_untaxed'))
        total_qty = sum(lines.mapped('product_uom_qty'))
        total_customers = len(orders.mapped('partner_id'))

        # 1. Daily Breakdown
        daily_groups = {}
        for line in lines:
            order_date = line.order_id.date_order.date()
            if order_date not in daily_groups:
                daily_groups[order_date] = {
                    'date': order_date,
                    'order_ids': set(),
                    'partners': set(),
                    'qty': 0.0,
                    'untaxed': 0.0,
                    'total': 0.0,
                    'lines_count': 0,
                }
            g = daily_groups[order_date]
            g['order_ids'].add(line.order_id.id)
            g['partners'].add(line.order_id.partner_id.name)
            g['qty'] += line.product_uom_qty
            g['untaxed'] += line.price_subtotal
            g['total'] += line.price_total
            g['lines_count'] += 1

        daily_data = []
        for d in sorted(daily_groups.keys()):
            g = daily_groups[d]
            daily_data.append({
                'date': d.strftime('%Y-%m-%d'),
                'orders_count': len(g['order_ids']),
                'customers_display': ", ".join(list(g['partners'])[:3]) + ("..." if len(g['partners']) > 3 else ""),
                'qty': g['qty'],
                'untaxed': g['untaxed'],
                'total': g['total'],
            })

        # 2. Customer Breakdown
        customer_groups = {}
        for line in lines:
            partner = line.order_id.partner_id
            if partner.id not in customer_groups:
                customer_groups[partner.id] = {
                    'partner': partner,
                    'order_ids': set(),
                    'qty': 0.0,
                    'untaxed': 0.0,
                    'total': 0.0,
                    'products': set(),
                }
            cg = customer_groups[partner.id]
            cg['order_ids'].add(line.order_id.id)
            cg['qty'] += line.product_uom_qty
            cg['untaxed'] += line.price_subtotal
            cg['total'] += line.price_total
            cg['products'].add(line.product_id.display_name)

        customer_data = []
        for pid in sorted(customer_groups.keys(), key=lambda x: customer_groups[x]['total'], reverse=True):
            cg = customer_groups[pid]
            customer_data.append({
                'partner_name': cg['partner'].name,
                'customer_code': getattr(cg['partner'], 'ref', False) or '',
                'orders_count': len(cg['order_ids']),
                'qty': cg['qty'],
                'untaxed': cg['untaxed'],
                'total': cg['total'],
                'products_count': len(cg['products']),
            })

        # 3. Product Breakdown
        product_groups = {}
        for line in lines:
            prod = line.product_id
            if prod.id not in product_groups:
                sec_parts = prod.secondary_part_number_ids.filtered(lambda r: r.part_type == 'secondary' and r.name)
                sec_display_list = []
                for sp in sec_parts:
                    if sp.note:
                        sec_display_list.append(f"{sp.name} ({sp.note})")
                    else:
                        sec_display_list.append(sp.name)

                product_groups[prod.id] = {
                    'product': prod,
                    'product_code': prod.default_code or '',
                    'part_number': prod.part_number or '',
                    'name': prod.name,
                    'image_128': prod.image_128,
                    'secondary_parts': ", ".join(sec_display_list) if sec_display_list else False,
                    'has_secondary': bool(sec_display_list),
                    'qty': 0.0,
                    'uom': line.product_uom_id.name if line.product_uom_id else prod.uom_id.name,
                    'untaxed': 0.0,
                    'total': 0.0,
                }
            pg = product_groups[prod.id]
            pg['qty'] += line.product_uom_qty
            pg['untaxed'] += line.price_subtotal
            pg['total'] += line.price_total

        product_data = []
        for prod_id in sorted(product_groups.keys(), key=lambda x: product_groups[x]['total'], reverse=True):
            pg = product_groups[prod_id]
            avg_price = (pg['untaxed'] / pg['qty']) if pg['qty'] else 0.0
            product_data.append({
                'product_id': pg['product'].id,
                'product_code': pg['product_code'],
                'part_number': pg['part_number'],
                'name': pg['name'],
                'image_128': pg['image_128'],
                'secondary_parts': pg['secondary_parts'],
                'has_secondary': pg['has_secondary'],
                'qty': pg['qty'],
                'uom': pg['uom'],
                'avg_price': avg_price,
                'untaxed': pg['untaxed'],
                'total': pg['total'],
            })

        return {
            'company': self.company_id,
            'report_type': self.report_type,
            'date_from': self.date_from.strftime('%d/%m/%Y'),
            'date_to': self.date_to.strftime('%d/%m/%Y'),
            'order_state': dict(self._fields['order_state'].selection).get(self.order_state),
            'currency': self.company_id.currency_id,
            'kpis': {
                'total_orders': total_orders,
                'total_revenue': total_amount,
                'total_untaxed': total_untaxed,
                'total_qty': total_qty,
                'total_customers': total_customers,
                'avg_order_value': (total_amount / total_orders) if total_orders else 0.0,
            },
            'daily_data': daily_data,
            'customer_data': customer_data,
            'product_data': product_data,
        }
