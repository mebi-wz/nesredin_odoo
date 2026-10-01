from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class LocalPurchaseRequisition(models.Model):
    _name = 'local.purchase.requisition'
    _description = 'Purchase Requisition'
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
        readonly=False,
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
    procurement_method = fields.Selection(
        [
            ('rfq', 'RFQ'),
            ('po', 'Direct PO'),
        ],
        string='Procurement Method',
        default='rfq',
        tracking=True,
        required=True
    )
    
    purchase_type = fields.Selection(
        [
            ('goods', 'Goods'),
            ('service', 'Service'),
        ],
        string='Purchase Type',
        default='goods',
        tracking=True,
        required=True
    )
    purpose = fields.Text(string='Purpose')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Waiting Dept Manager Approval'),
        ('verified', 'Waiting Finance Approval'),
        ('pr_manager_approved', 'Waiting CEO Approval'),
        ('approved', 'Ready for Procurement'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)
    product_type = fields.Selection(
        [
            ('consu', 'Goods'),
            ('service', 'Service'),
        ],
        string='Product Type',
        default='consu',
        tracking=True,
        required=True
    )

    line_ids = fields.One2many(
        'local.purchase.requisition.line',
        'requisition_id',
        string='Products',
        tracking=True
    )

    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True, tracking=True)

    po_ids = fields.One2many('purchase.order', 'local_purchase_request_id', string='Purchase Orders')
    po_count = fields.Integer(compute='_compute_po_count')
    
    store_requisition_id = fields.Many2one('store.requisition', string='Source Store Requisition', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    @api.depends('po_ids')
    def _compute_po_count(self):
        for rec in self:
            rec.po_count = len(rec.po_ids)

    @api.depends('line_ids.total_price')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('total_price'))


    def action_create_rfq(self):
        self.ensure_one()
        return self.action_create_po()

    def action_create_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'context': {
                'default_local_purchase_request_id': self.id,
                'default_origin': self.name,
                'default_request_type': 'local',
                'default_order_line': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.product_id.with_context(lang=self.env.user.lang).description_pickingin or line.product_id.display_name,
                        'product_qty': line.quantity,
                        'price_unit': line.unit_price,
                        'product_uom_id': line.product_uom_id.id,
                        'date_planned': fields.Datetime.now(),
                        'analytic_distribution': {str(line.cost_center_id.id): 100} if line.cost_center_id else False,
                    }) for line in self.line_ids
                ]
            },
        }

    def action_view_pos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('local_purchase_request_id', '=', self.id)],
            'context': {'default_local_purchase_request_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id') or self.env.company.id
                self._ensure_company_sequence(company_id)
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('local.purchase.requisition') or 'New'
        return super().create(vals_list)

    def _ensure_company_sequence(self, company_id):
        """Automatically create a separate sequence for a company if it doesn't exist."""
        Sequence = self.env['ir.sequence'].sudo()
        exists = Sequence.search([('code', '=', 'local.purchase.requisition'), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', 'local.purchase.requisition'), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    def action_approve(self):
        self.ensure_one()

        state_map = {
            'draft': 'submitted',
            'submitted': 'verified',        # Dept Manager → Finance
            'pr_manager_approved': 'approved',         # CEO → approved
        }

        # Threshold check: now happens after Finance Approval ('verified')
        if self.state == 'verified':
            threshold = self.company_id.pr_ceo_approval_threshold
            if threshold and self.amount_total <= threshold:
                next_state = 'approved'  # skip CEO
                self.message_post(
                    body=_("CEO approval skipped as amount (%.2f) is below or equal to threshold (%.2f).") 
                    % (self.amount_total, threshold)
                )
            else:
                next_state = 'pr_manager_approved'  # go to CEO
        else:
            next_state = state_map.get(self.state)

        if next_state:
            self.write({'state': next_state})
            self.message_post(body=_(self._description + " moved to %s by %s" % (next_state.replace('_', ' ').capitalize(), self.env.user.name)))
            self._notify_next_approver(next_state)
        else:
            raise UserError(_("No further processing step for the current state."))
        
    def action_submit(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("You must add at least one product line before submitting the requisition."))
        if self.state == 'draft':
            if not self.department_id:
                raise ValidationError(_("Please specify the requesting Department before submitting."))
            if not self.cost_center_id:
                raise ValidationError(_("Please specify the Cost Center before submitting."))
            for line in self.line_ids:
                if line.unit_price <= 0:
                    raise ValidationError(_("Product %s has zero or negative price. 0 price is not allowed.") % line.product_id.name)

            self.write({'state': 'submitted'})
            self.message_post(body=_("Requisition submitted by %s" % self.env.user.name))
            # Notify next approvers
            self._notify_next_approver('submitted')

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
            'submitted':          'procurement_local_purchase.group_local_purchase_dept_manager',  # Dept Manager
            'verified':           'procurement_store_requisition.group_store_requisition_budget_manager',  # Finance
            'pr_manager_approved': 'procurement_local_purchase.group_local_purchase_ceo',          # CEO
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
                summary=_("PR Approval Required"),
                note=_("A local purchase requisition (%s) is awaiting your action.") % (self.name)
            )
        
        # Also post to chatter for history
        self.message_post(
            body=_("Approval activity scheduled for: %s") % ", ".join(users.mapped('name')),
            message_type='notification'
        )

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

class LocalPurchaseRequisitionLine(models.Model):
    _name = 'local.purchase.requisition.line'
    _description = 'Local Purchase Requisition Line'

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
        'local.purchase.requisition',
        string='Requisition',
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('type', '=', parent.product_type), ('landed_cost_ok', '=', False), ('is_active_product', '=', True)]",
        required=True
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

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # description and product_uom_id are plain stored fields (not related),
            # so writing here is safe and does NOT propagate to product.product.
            self.description = self.product_id.name
            self.product_uom_id = self.product_id.uom_id

    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string='Cost Center',
        related='requisition_id.cost_center_id',
        store=True
    )
    unit_price = fields.Float(string='Unit Price', default=0.0 )
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    budget_category_id = fields.Many2one(
        'account.budget.post', 
        string='Budgetary Position',
        ondelete='set null'
    )  
    analytic_line_ids = fields.One2many(
        'account.analytic.line',
        'requisition_line_id',
        string='Analytic Lines'
    )
    remaining_budget = fields.Float(
        string="Remaining Budget",
        compute="_compute_remaining_budget",
        store=False
    )   
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', store=True, readonly=True)
    state = fields.Selection(related='requisition_id.state', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='requisition_id.company_id',
        store=True,
        readonly=True
    )

    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.quantity * rec.unit_price
    @api.depends('budget_category_id', 'total_price', 'cost_center_id', 'requisition_id.date_requisition', 'requisition_id.line_ids.total_price', 'requisition_id.line_ids.budget_category_id', 'requisition_id.line_ids.cost_center_id')
    def _compute_remaining_budget(self):
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
                    line.remaining_budget = planned_amount + practical_amount - req_total
                else:
                    req_total = sum(
                        l.total_price for l in line.requisition_id.line_ids
                        if l.budget_category_id == line.budget_category_id
                        and l.cost_center_id == line.cost_center_id
                    )
                    line.remaining_budget = -req_total
            else:
                line.remaining_budget = 0.0

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

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    local_purchase_request_id = fields.Many2one('local.purchase.requisition', string='Source Local Requisition')

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        _logger.info("StockPicking button_validate called for %s", self.mapped('name'))
        res = super(StockPicking, self).button_validate()
        for picking in self:
            _logger.info("Processing picking %s, state: %s, type: %s", picking.name, picking.state, picking.picking_type_id.code)
            # Check if this is an incoming picking (receipt)
            # Standard Odoo field picking_type_id.code is 'incoming' for receipts
            if picking.picking_type_id.code == 'incoming' and picking.state == 'done':
                # Traverse back to Store Requisition
                # Path 1: Direct PO -> Local PR
                # Path 2: RFQ PO -> RFQ -> Local PR
                po = picking.purchase_id
                pr = False
                if po:
                    if 'local_purchase_request_id' in po._fields and po.local_purchase_request_id:
                        pr = po.local_purchase_request_id
                    elif 'local_rfq_id' in po._fields and po.local_rfq_id and hasattr(po.local_rfq_id, 'requisition_id'):
                        pr = po.local_rfq_id.requisition_id
                
                if pr:
                    _logger.info("Found related Local PR %s for picking %s", pr.name, picking.name)
                    if pr.store_requisition_id:
                        requisition = pr.store_requisition_id
                        _logger.info("Found related Store Requisition %s. Current state: %s", requisition.name, requisition.state)
                        # Only reset if it's in 'waiting' state
                        if requisition.state == 'waiting':
                            _logger.info("Resetting Store Requisition %s to budget_approved", requisition.name)
                            requisition.write({'state': 'budget_approved'})
                            requisition.message_post(
                                body=_("Stock arrived for shortage items (Reference: %s). Requisition is now ready for further issuance.") % picking.name
                            )
                        else:
                            _logger.info("Store Requisition %s is NOT in 'waiting' state. Skipping reset.", requisition.state)
                    else:
                        _logger.info("Local PR %s has no Store Requisition link.", pr.name)
                else:
                    _logger.info("Picking %s (PO: %s) has no related Local PR (checked local_purchase_request_id and local_rfq_id).", picking.name, po.name if po else 'None')
        return res
