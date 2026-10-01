from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ForeignPurchaseRequisition(models.Model):
    _name = 'foreign.purchase.requisition'
    _description = 'Foreign Purchase Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True
    )
    date_requisition = fields.Date(
        string='Requisition Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        tracking=True,
        ondelete='set null'
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        store=True,
        tracking=True
    )
    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        store=True,
        tracking=True
    )
    purpose = fields.Selection(
        [
            ('refill','Refill'),
            ('tender','Tender'),
            ('emergency','Emergency')
        ],string="Request Purpose", tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Waiting Manager Verification'),
        ('manager_verified', 'Waiting Finance Approval'),
        ('budget_approved', 'Waiting CEO Approval'),
        ('approved', 'Ready for Procurement'),
        ('rfq_created', 'RFQ Created'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)

    line_ids = fields.One2many(
        'foreign.purchase.requisition.line',
        'requisition_id',
        string='Products',
        tracking=True
    )
    po_ids = fields.One2many('purchase.order', 'foreign_purchase_request_id', string='Purchase Orders')
    po_count = fields.Integer(compute='_compute_po_count')

    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    current_market_ids = fields.One2many(
        'current.market.analysis',
        'requisition_id',
        string="Current Market Analysis"
    )

    future_market_ids = fields.One2many(
        'future.market.analysis',
        'requisition_id',
        string="Future Market Analysis"
    )
    product_type = fields.Selection(
        [('consu', 'Goods'), ('service', 'Service')],
        string="Product Type",
        required=True,
        tracking=True,
        default='consu'
    )
    current_market_count = fields.Integer(compute='_compute_market_counts')
    future_market_count = fields.Integer(compute='_compute_market_counts')

    @api.depends('po_ids')
    def _compute_po_count(self):
        for rec in self:
            rec.po_count = len(rec.po_ids)

    def _compute_market_counts(self):
        for rec in self:
            rec.current_market_count = len(rec.current_market_ids)
            rec.future_market_count = len(rec.future_market_ids)

    @api.depends('line_ids.total_price')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('total_price'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id') or self.env.company.id
                self._ensure_company_sequence(company_id)
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('foreign.purchase.requisition') or 'PR-DF0001'
        return super().create(vals_list)

    def _ensure_company_sequence(self, company_id):
        Sequence = self.env['ir.sequence'].sudo()
        code = 'foreign.purchase.requisition'
        exists = Sequence.search([('code', '=', code), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', code), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    def action_approve(self):
        self.ensure_one()

        # Validation: Check if there are any products before proceeding
        if not self.line_ids:
            raise ValidationError(_("You cannot proceed without adding at least one product."))

        # Validation checks based on the current state before transitioning
        if self.state == 'draft':
            if not self.department_id:
                raise ValidationError(_("Please specify the requesting Department before submitting."))
            if not self.cost_center_id:
                raise ValidationError(_("Please specify the Cost Center before submitting."))
            for line in self.line_ids:
                if line.unit_price <= 0:
                    raise ValidationError(_("Product %s has zero or negative price. 0 price is not allowed.") % line.product_id.name)

            # Validation: Block negative margins
            for line in self.line_ids:
                if line.margin < 0:
                    raise ValidationError(_("You cannot proceed with a negative margin for product: %s. Please adjust the Estimated Selling Price or Unit Price.") % line.product_id.display_name)

            # Validation: At least one market analysis must exist before submission
            

        elif self.state == 'submitted':
            pass # Verification step, move to manager_verified

        elif self.state == 'manager_verified':
            pass

        state_map = {
            'draft': 'submitted',
            'submitted': 'manager_verified',
            'manager_verified': 'budget_approved',
            'budget_approved': 'approved',
        }
        next_state = state_map.get(self.state)
        if next_state:
            self.write({'state': next_state})
            self.message_post(body=_(self._description + " moved to %s by %s" % (next_state.replace('_', ' ').capitalize(), self.env.user.name)))
            self._notify_next_approver(next_state)
        else:
            raise UserError(_("No further processing step for the current state."))

    def _notify_next_approver(self, next_state):
        # Clear old activities for this record first
        self.activity_unlink(['mail.mail_activity_data_todo'])

        # Notify requester of the update
        requester_user = self.requested_by if self.requested_by else self.create_uid
        if requester_user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester_user.id,
                summary=_("Requisition Update: %s") % self.name,
                note=_("Your requisition (%s) is now in state: %s.") % (self.name, next_state.replace('_', ' ').replace('-', ' ').capitalize())
            )

        group_xmlid_map = {
            'submitted': 'procurement_foreign_purchase.group_foreign_purchase_manager',
            'manager_verified': 'procurement_foreign_purchase.group_foreign_purchase_budget',
            'budget_approved': 'procurement_foreign_purchase.group_foreign_purchase_ceo',
        }
        
        group_xmlid = group_xmlid_map.get(next_state)
        if not group_xmlid:
            return

        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        # Find users in the group
        company_id = self.sudo().company_id.id
        users = group.sudo().user_ids.filtered(lambda u: u.company_id.id == company_id or company_id in u.company_ids.ids)
        if not users:
            return

        # Schedule new activities for each user in the group
        for user in users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_("Foreign PR Approval Required"),
                note=_("A foreign purchase requisition (%s) is awaiting your action.") % (self.name)
            )
        
        # Also post to chatter for history
        self.message_post(
            body=_("Approval activity scheduled for: %s") % ", ".join(users.mapped('name')),
            message_type='notification'
        )

    def action_reject(self):
        self.ensure_one()
        self.write({'state': 'rejected'})
        self.message_post(body=_(self._description + " rejected / returned by %s" % self.env.user.name))
        self._notify_next_approver('rejected')

    def action_cancel(self):
        self.ensure_one()
        self.write({'state': 'cancelled'})
        self.message_post(body=_(self._description + " cancelled by %s" % self.env.user.name))
        self._notify_next_approver('cancelled')

    def action_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})
        self.message_post(body=_(self._description + " reset to draft by %s" % self.env.user.name))
        self._notify_next_approver('draft')

    def action_create_po(self):
        self.ensure_one()

        # Block lines with zero or negative margin (0 birr profit)
        zero_margin_lines = self.line_ids.filtered(lambda l: l.margin <= 0)
        if zero_margin_lines:
            product_names = ', '.join(zero_margin_lines.mapped('product_id.display_name'))
            raise ValidationError(_(
                "The following products have zero or negative margin and cannot be sent to a Purchase Order:\n\n"
                "%s\n\nPlease set a valid Estimated Selling Price higher than the Unit Price before proceeding."
            ) % product_names)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Order'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'context': {
                'default_origin': self.name,
                'default_foreign_purchase_request_id': self.id,
                'default_order_line': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.product_id.display_name,
                        'product_qty': line.quantity,
                        'price_unit': line.unit_price,
                        'product_uom_id': line.product_uom_id.id,
                        'analytic_distribution': {str(line.cost_center_id.id): 100} if line.cost_center_id else False,
                    })
                    for line in self.line_ids
                ],
            }
        }

    def action_view_pos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('foreign_purchase_request_id', '=', self.id)],
            'context': {'default_foreign_purchase_request_id': self.id},
        }

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    foreign_purchase_request_id = fields.Many2one('foreign.purchase.requisition', string='Source Foreign Requisition')

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
   
    customs_product_cost = fields.Float(
        string='Customs Product Cost',
        help='The value assigned by customs during import clearance.'
    )
    cost_difference = fields.Float(
        string='Cost Difference',
        compute='_compute_cost_difference',
        store=True,
        help='Customs Product Cost - Actual Product Cost'
    )

    @api.depends('customs_product_cost', 'price_unit')
    def _compute_cost_difference(self):
        for rec in self:
            etb_price = rec.price_unit * (rec.order_id.exchange_rate or 1.0)
            rec.cost_difference = rec.customs_product_cost - etb_price

class ForeignPurchaseRequisitionLine(models.Model):
    _name = 'foreign.purchase.requisition.line'
    _description = 'Foreign Purchase Requisition Line'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sanitize_analytic_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sanitize_analytic_vals(vals)
        return super().write(vals)

    @api.model
    def _sanitize_analytic_vals(self, vals):
        """Remove or fix any analytic_distribution / plan column values that may
        arrive as display-name strings (e.g. '[0003] Finance') instead of the
        required JSON dict format, preventing a PostgreSQL 'invalid input syntax
        for type json' error."""
        import json
        fields_to_check = [k for k in list(vals.keys())
                           if k == 'analytic_distribution' or k.startswith('x_plan_')]
        for field_name in fields_to_check:
            val = vals[field_name]
            if val is False or val is None:
                continue
            if isinstance(val, str):
                # A string value is never valid for a JSON column — strip it.
                vals.pop(field_name)
            elif isinstance(val, dict):
                # Ensure dict keys are all valid stringified integers.
                cleaned = {}
                for k, v in val.items():
                    try:
                        int(k.split(',')[0])  # raises if not numeric
                        cleaned[k] = v
                    except (ValueError, AttributeError):
                        pass  # Drop invalid keys (e.g. display names)
                vals[field_name] = cleaned or False

    requisition_id = fields.Many2one(
        'foreign.purchase.requisition',
        string='Requisition',
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Requested Products',
        domain="[('type', '=', parent.product_type), ('landed_cost_ok', '=', False), ('is_active_product', '=', True)]",
        required=True
    )
    analytic_line_ids = fields.One2many(
        'account.analytic.line',
        'requisition_line_id',
        string='Analytic Lines'
    )
    description = fields.Char(string='Description', store=True, translate=True)
    account_id = fields.Many2one('account.account', string='GL Account', compute='_compute_account_id', store=True, readonly=False)

    @api.depends('product_id')
    def _compute_account_id(self):
        for line in self:
            if line.product_id:
                line.account_id = line.product_id.property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
            else:
                line.account_id = False
    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        related='requisition_id.cost_center_id',
        store=False
    )
    budget_category_id = fields.Many2one(
        'account.budget.post', 
        string='Budgetary Position',
        ondelete='set null'
    )  
    remaining_budget = fields.Float(string='Remaining Budget', compute='_compute_remaining_budget', store=False)
    unit_price = fields.Float(string='Unit Price', default=0.0 )
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)
    quantity = fields.Float(string='Qty', default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='UoM', store=True, readonly=True)
    remark = fields.Text(string='Remark')
    state = fields.Selection(related='requisition_id.state', store=True)
    line_no = fields.Integer(
        string="Line No",
        compute="_compute_line_no",
        store=True
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # description and product_uom_id are plain stored fields (not related),
            # so writing here is safe and does NOT propagate to product.product.
            self.description = self.product_id.name
            self.product_uom_id = self.product_id.uom_id
            # Auto fill unit price from product standard price (cost)
            self.unit_price = self.product_id.standard_price

    order_qty_and_current_stock= fields.Float(string="Order Qty and Current Stock",compute='_compute_ordered_and_stock_qty')
    four_month_qty = fields.Float(
        string="4 Month Consumption",
        compute="_compute_period_consumption",
        store=False,
        readonly=True
    )

    six_month_qty = fields.Float(
        string="6 Month Consumption",
        compute="_compute_period_consumption",
        store=False,
        readonly=True
    )
    @api.depends('product_id', 'requisition_id.company_id')
    def _compute_period_consumption(self):
        for rec in self:
            if rec.product_id and rec.requisition_id.company_id:
                product = rec.product_id.with_company(
                    rec.requisition_id.company_id
                )
                monthly = rec.avg_monthly_consumption or 0.0

                rec.four_month_qty = monthly * 4
                rec.six_month_qty = monthly * 6
            else:
                rec.four_month_qty = 0.0
                rec.six_month_qty = 0.0
    @api.depends('requisition_id','quantity','product_id','current_balance')
    def _compute_ordered_and_stock_qty(self):
        for rec in self:
            rec.order_qty_and_current_stock = rec.quantity + rec.current_balance
    @api.depends('requisition_id', 'requisition_id.line_ids')
    def _compute_line_no(self):
        for requisition in self.mapped('requisition_id'):
            for index, line in enumerate(requisition.line_ids.sorted('id'), start=1):
                line.line_no = index

    is_budget_product = fields.Boolean(string="Budget Product?")
    is_core_product = fields.Boolean(string="Core Product?")

    avg_monthly_consumption = fields.Float(
        string="Average Monthly Consumption",
        compute="_compute_avg_monthly_consumption",
        store=True
    )

    @api.depends('product_id', 'requisition_id.company_id')
    def _compute_avg_monthly_consumption(self):
        for rec in self:
            if rec.product_id:
                rec.avg_monthly_consumption = rec.product_id.with_company(
                    rec.requisition_id.company_id
                ).product_tmpl_id.avg_monthly_consumption or 0.0
            else:
                rec.avg_monthly_consumption = 0.0

    @api.depends('product_id', 'requisition_id.company_id')
    def _compute_period_consumption(self):
        for rec in self:
            if rec.product_id and rec.requisition_id.company_id:
                product_template = rec.product_id.product_tmpl_id.with_company(
                    rec.requisition_id.company_id
                )
                monthly = getattr(product_template, 'avg_monthly_consumption', 0.0)

                rec.four_month_qty = monthly * 4
                rec.six_month_qty = monthly * 6
            else:
                rec.four_month_qty = 0.0
                rec.six_month_qty = 0.0
    current_balance = fields.Float(
        string="Current Balance",
        compute="_compute_current_balance",
        store=False,
        readonly=True   
    )

    @api.depends('product_id', 'requisition_id.company_id')
    def _compute_current_balance(self):
        for rec in self:
            if rec.product_id and rec.requisition_id.company_id:
                product = rec.product_id.with_company(
                    rec.requisition_id.company_id
                )
                rec.current_balance = product.qty_available
            else:
                rec.current_balance = 0.0
   
    estimated_selling_price = fields.Float(string="Estimated Selling Price")

    margin = fields.Float(
        string="Margin (%)",
        compute="_compute_margin",
        store=True
    )

    arrival_time = fields.Date(string="Arrival Time")

    @api.depends('estimated_selling_price', 'unit_price')
    def _compute_margin(self):
        for rec in self:
            if rec.estimated_selling_price:
                rec.margin = ((rec.estimated_selling_price - rec.unit_price) / rec.estimated_selling_price) * 100
            else:
                rec.margin = 0.0
    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.quantity * rec.unit_price
    
    @api.depends(
        'budget_category_id',
        'total_price',
        'quantity',
        'unit_price',
        'cost_center_id',
        'requisition_id.date_requisition',
        'requisition_id.line_ids.total_price',
        'requisition_id.line_ids.budget_category_id',
        'requisition_id.line_ids.cost_center_id'
    )
    def _compute_remaining_budget(self):
        # Step 1: collect all needed keys
        all_lines = self.filtered(lambda l: l.budget_category_id and l.cost_center_id and l.requisition_id.date_requisition)

        if not all_lines:
            for line in self:
                line.remaining_budget = 0.0
            return

        categories = all_lines.mapped('budget_category_id').ids
        cost_centers = all_lines.mapped('cost_center_id').ids
        dates = all_lines.mapped('requisition_id.date_requisition')

        min_date = min(dates)
        max_date = max(dates)

        # Step 2: single search (no more database abuse)
        budget_lines = self.env['budget.lines'].search([
            ('general_budget_id', 'in', categories),
            ('analytic_account_id', 'in', cost_centers),
            ('date_from', '<=', max_date),
            ('date_to', '>=', min_date)
        ])

        # Step 3: group budget data
        budget_map = {}
        for bl in budget_lines:
            key = (bl.general_budget_id.id, bl.analytic_account_id.id)
            if key not in budget_map:
                budget_map[key] = {
                    'planned': 0.0,
                    'practical': 0.0
                }
            budget_map[key]['planned'] += bl.planned_amount
            budget_map[key]['practical'] += bl.practical_amount

        # Step 4: process per requisition (efficient running total)
        for req in self.mapped('requisition_id'):
            sorted_lines = req.line_ids.sorted(lambda l: l.id or 0)

            running_map = {}

            for l in sorted_lines:
                key = (l.budget_category_id.id, l.cost_center_id.id)

                if key not in running_map:
                    running_map[key] = 0.0

                running_map[key] += l.total_price

                if l in self:
                    budget_data = budget_map.get(key)

                    if budget_data:
                        l.remaining_budget = (
                            budget_data['planned']
                            + budget_data['practical']
                            - running_map[key]
                        )
                    else:
                        l.remaining_budget = -running_map[key]

    @api.constrains('total_price', 'budget_category_id')
    def _check_budget_limit(self):
        for line in self:
            if line.budget_category_id and line.cost_center_id and line.requisition_id.date_requisition:
                req_date = line.requisition_id.date_requisition
                budget_lines = self.env['budget.lines'].search([
                    ('general_budget_id', '=', line.budget_category_id.id),
                    ('analytic_account_id', '=', line.cost_center_id.id),
                    ('date_from', '<=', req_date),
                    ('date_to', '>=', req_date)
                ])

                if budget_lines:
                    planned_amount = sum(budget_lines.mapped('planned_amount'))
                    practical_amount = sum(budget_lines.mapped('practical_amount'))
                    req_total = sum(
                        l.total_price for l in line.requisition_id.line_ids
                        if l.budget_category_id == line.budget_category_id
                        and l.cost_center_id == line.cost_center_id
                    )
                    if (abs(practical_amount) + req_total) > planned_amount:
                        raise ValidationError(
                            _("Budget exceeded for Budgetary Position '%s' and Cost Center '%s'. Planned: %.2f, Used: %.2f, Requested: %.2f") % 
                            (line.budget_category_id.name, line.cost_center_id.name, planned_amount, abs(practical_amount), req_total)
                        )
                else:
                    raise ValidationError(
                        _("No budget line found for Budgetary Position '%s' and Cost Center '%s' for the requisition date %s.") %
                        (line.budget_category_id.name, line.cost_center_id.name, req_date)
                    )
    def open_current_market_analysis(self):
        self.ensure_one()
        record = self.env['current.market.analysis'].search(
            [('requisition_line_id', '=', self.id), ('product_id', '=', self.product_id.id)],
            limit=1
        )
        if record:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'current.market.analysis',
                'view_mode': 'form',
                'res_id': record.id,
                'target': 'new',  # modal
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'current.market.analysis',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_requisition_line_id': self.id,
                    'default_product_id': self.product_id.id
                },
            }

    def open_future_market_analysis(self):
        self.ensure_one()
        record = self.env['future.market.analysis'].search(
            [('requisition_line_id', '=', self.id), ('product_id', '=', self.product_id.id)],
            limit=1
        )
        if record:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'future.market.analysis',
                'view_mode': 'form',
                'res_id': record.id,
                'target': 'new',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'future.market.analysis',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_requisition_line_id': self.id,
                    'default_product_id': self.product_id.id
                },
            }
    def action_open_potential_vendors(self):
        self.ensure_one()

        potential = self.env['potential.vendors'].search([
            ('requisition_line_id', '=', self.id)
        ], limit=1)

        if not potential:
            potential = self.env['potential.vendors'].create({
                'requisition_line_id': self.id
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Potential Vendors',
            'res_model': 'potential.vendors',
            'view_mode': 'form',
            'res_id': potential.id,
            'target': 'new',   # opens modal
        }
