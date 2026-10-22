# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError


class SaleOrderReturnWizard(models.TransientModel):
    _name = 'sale.order.return.wizard'
    _description = 'Sales Order Return Wizard'

    order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        related='order_id.partner_id',
        string='Customer',
        readonly=True,
    )
    available_invoice_ids = fields.Many2many(
        'account.move',
        compute='_compute_available_invoices',
        string='Available Invoices',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Original Invoice to Reverse',
        domain="[('id', 'in', available_invoice_ids)]",
        help="Select the original customer invoice being returned/reversed.",
    )
    reason = fields.Char(
        string='Return Reason',
        required=True,
    )
    line_ids = fields.One2many(
        'sale.order.return.wizard.line',
        'wizard_id',
        string='Return Items',
    )

    @api.depends('order_id')
    def _compute_available_invoices(self):
        for wiz in self:
            if wiz.order_id:
                wiz.available_invoice_ids = wiz.order_id.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
                )
            else:
                wiz.available_invoice_ids = self.env['account.move']

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id') or res.get('order_id')
        if order_id:
            order = self.env['sale.order'].browse(order_id)
            # Default to the most recent posted customer invoice if available
            posted_invoices = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
            )
            if posted_invoices:
                res['invoice_id'] = posted_invoices[0].id

            lines_vals = []
            for line in order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment):
                prior_returns = order.return_order_ids.filtered(lambda r: r.state != 'cancel')
                already_ret = 0.0
                for r in prior_returns:
                    matching = r.order_line.filtered(lambda rl: rl.product_id == line.product_id)
                    already_ret += sum(matching.mapped('product_uom_qty'))

                delivered_or_ordered = line.qty_delivered if line.qty_delivered > 0 else line.product_uom_qty
                max_ret = max(0.0, delivered_or_ordered - already_ret)
                if max_ret > 0:
                    lines_vals.append((0, 0, {
                        'sale_line_id': line.id,
                        'product_id': line.product_id.id,
                        'qty_ordered': line.product_uom_qty,
                        'qty_delivered': line.qty_delivered,
                        'qty_already_returned': already_ret,
                        'max_returnable_qty': max_ret,
                        'qty_to_return': max_ret,
                        'uom_id': (line.product_uom_id or line.product_id.uom_id).id,
                        'price_unit': line.price_unit,
                    }))
            res['line_ids'] = lines_vals
        return res

    def action_create_return_order(self):
        self.ensure_one()
        lines_to_return = self.line_ids.filtered(lambda l: l.qty_to_return > 0)
        if not lines_to_return:
            raise UserError(_("Please enter at least one quantity greater than 0 to return."))

        for l in lines_to_return:
            if l.max_returnable_qty > 0 and l.qty_to_return > l.max_returnable_qty:
                raise UserError(_(
                    "You cannot return more than %(max).2f for product %(product)s."
                ) % {'max': l.max_returnable_qty, 'product': l.product_id.display_name})

        orig = self.order_id

        # Generate return name reference
        return_name = _("RET-%s") % orig.name

        return_vals = {
            'name': return_name,
            'is_return': True,
            'original_sale_order_id': orig.id,
            'original_invoice_id': self.invoice_id.id if self.invoice_id else False,
            'partner_id': orig.partner_id.id,
            'partner_invoice_id': orig.partner_invoice_id.id,
            'partner_shipping_id': orig.partner_shipping_id.id,
            'warehouse_id': orig.warehouse_id.id,
            'analytic_account_id': orig.analytic_account_id.id if hasattr(orig, 'analytic_account_id') else False,
            'pricelist_id': orig.pricelist_id.id,
            'company_id': orig.company_id.id,
            'user_id': self.env.user.id,
            'team_id': orig.team_id.id,
            'return_reason': self.reason,
            'state': 'draft',
            'order_line': [],
        }

        if hasattr(orig, 'sale_type') and orig.sale_type:
            return_vals['sale_type'] = orig.sale_type
            if orig.sale_type == 'cash':
                return_vals['payment_note'] = _("Sales Return for %s") % orig.name

        for wl in lines_to_return:
            sol = wl.sale_line_id
            product = wl.product_id or (sol and sol.product_id)
            if not product and orig:
                continue

            if not sol and orig and product:
                sol = orig.order_line.filtered(lambda l: l.product_id == product)[:1]

            name = (sol and sol.name) or product.display_name
            tax_records = (getattr(sol, 'tax_ids', False) or getattr(sol, 'tax_id', False)) if sol else False
            tax_ids = [Command.set(tax_records.ids)] if tax_records else []
            discount = (sol.discount if hasattr(sol, 'discount') else 0.0) if sol else 0.0
            uom = wl.uom_id or (sol and (sol.product_uom_id or sol.product_id.uom_id)) or product.uom_id
            price = wl.price_unit or (sol and sol.price_unit) or product.list_price

            line_dict = {
                'product_id': product.id,
                'name': name,
                'product_uom_qty': wl.qty_to_return,
                'product_uom_id': uom.id,
                'price_unit': price,
                'tax_ids': tax_ids,
                'discount': discount,
            }
            if sol and sol.analytic_distribution:
                line_dict['analytic_distribution'] = sol.analytic_distribution
            return_vals['order_line'].append(Command.create(line_dict))

        return_order = self.env['sale.order'].create(return_vals)

        # Post chatter notes
        orig.message_post(
            body=Markup(_("Return Sales Order <b>%s</b> created for Reason: <i>%s</i>.") % (return_order.name, self.reason))
        )
        return_order.message_post(
            body=Markup(_("Created as return for original Sales Order <b>%s</b>. Reason: <i>%s</i>.") % (orig.name, self.reason))
        )

        return {
            'name': _('Sales Return Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': return_order.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SaleOrderReturnWizardLine(models.TransientModel):
    _name = 'sale.order.return.wizard.line'
    _description = 'Sales Order Return Wizard Line'

    wizard_id = fields.Many2one(
        'sale.order.return.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Original Line',
        required=False,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=False,
    )
    part_number = fields.Char(
        string='Part Number',
        related='product_id.part_number',
        readonly=True,
    )
    qty_ordered = fields.Float(
        string='Ordered Qty',
        readonly=True,
    )
    qty_delivered = fields.Float(
        string='Delivered Qty',
        readonly=True,
    )
    qty_already_returned = fields.Float(
        string='Already Returned',
        readonly=True,
    )
    max_returnable_qty = fields.Float(
        string='Available to Return',
        readonly=True,
    )
    qty_to_return = fields.Float(
        string='Qty to Return',
        required=True,
        default=0.0,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        readonly=True,
    )
    price_unit = fields.Float(
        string='Unit Price',
        readonly=True,
    )
