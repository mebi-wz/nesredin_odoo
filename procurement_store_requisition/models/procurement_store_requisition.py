from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)
class StoreRequisition(models.Model):
    _name = 'store.requisition'
    _description = 'Store Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    
    @api.constrains('line_ids')
    def _check_lines_required(self):
        for rec in self:
            if not rec.line_ids:
                raise exceptions.ValidationError(
                    "You must add at least one product line before saving the requisition."
                )
    warehouse_id = fields.Many2one('stock.warehouse', string="Source Warehouse", required=True)
    location_id = fields.Many2one('stock.location', string="Source Location", related='warehouse_id.lot_stock_id', store=True)
    picking_ids = fields.One2many('stock.picking', 'store_requisition_id', string="Pickings (SIV)")
    picking_count = fields.Integer(compute='_compute_picking_count')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    request_type = fields.Selection(
        [
            ('local', 'Local'),
            ('foreign', 'Foreign'),
            ('pharmacy', 'Pharmacy'),
        ],
        string='Request Type',
        default='local',
        tracking=True
    )
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True
    )
    # can_approve = fields.Boolean(
    #     string="Can Approve",
    #     compute="_compute_can_approve",
    #     store=False
    # )
    # step_progress = fields.Html(
    #     string="Approval Progress",
    #     compute="_compute_step_progress",
    #     store=False
    # )
    date_requisition = fields.Datetime(
        string='Requisition Date',
        default=fields.Datetime.now(),
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
    is_requester = fields.Boolean(compute='_compute_is_requester')
    # approval_request_id = fields.Many2one('approval.request', string="Approval Request")
    
    def _compute_is_requester(self):
        for rec in self:
            rec.is_requester = rec.requested_by == self.env.user


    product_type = fields.Selection(
        [
            ('technical', 'Technical'),
            ('non-technical', 'Non-Technical'),
        ],
        string='Product Type',
        tracking=True
    )
    purpose = fields.Text(
        string='Purpose'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Waiting Dept Manager'),
        ('verified', 'Waiting Finance'),
        ('budget_approved', 'Waiting Store'),
        ('waiting', 'Waiting Procurement/Transfer'),
        ('processed', 'Processed'),
        ('received', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)

    line_ids = fields.One2many(
        'store.requisition.line',
        'requisition_id',
        string='Products',
        tracking=True
    )

    # approver_ids = fields.Many2many(
    #     related='approval_request_id.approver_ids',
    #     string="Current Approvers",
    #     tracking=True,
    #     store=False
    # )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id') or self.env.company.id
                self._ensure_company_sequence(company_id)
                # Correct way to get next sequence in multi-company environment
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('store.requisition') or 'New'
                _logger.info("Store Requisition: Generated sequence '%s' for company ID %s", vals['name'], company_id)
        return super().create(vals_list)

    def _ensure_company_sequence(self, company_id):
        """Automatically create a separate sequence for a company if it doesn't exist."""
        Sequence = self.env['ir.sequence'].sudo()
        exists = Sequence.search([('code', '=', 'store.requisition'), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', 'store.requisition'), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    # approval_request_id = fields.Many2one('approval.request', string="Approval Request")
     
    def action_approve(self):
        self.ensure_one()

        # Early Validations
        if self.state == 'draft':
            if not self.department_id:
                raise ValidationError(_("Please specify the requesting Department before submitting."))
            if not self.cost_center_id:
                raise ValidationError(_("Please specify the Cost Center before submitting."))
            for line in self.line_ids:
                if line.unit_price <= 0:
                    raise ValidationError(_("Product %s has zero or negative price. 0 price is not allowed.") % line.product_id.name)

        if self.state == 'verified':
            # Ensure GL account is selected before budget approval
            for line in self.line_ids:
                if not line.account_id:
                    raise ValidationError(_("Please select a GL Account for product %s before budget approval.") % line.product_id.name)
        
        if self.state == 'budget_approved':
            # This is now replaced by action_store_process for the Store step, 
            # but we keep it here for Received -> Closed or other simple steps.
            pass

        state_map = {
            'draft': 'submitted',
            'submitted': 'verified',
            'verified': 'budget_approved',
            'processed': 'received',
        }
        next_state = state_map.get(self.state)
        if next_state:
            self.write({'state': next_state})
            self.message_post(body=_(self._description + " moved to %s by %s" % (next_state.replace('_', ' ').capitalize(), self.env.user.name)))
            # Notify next approvers
            self._notify_next_approver(next_state)
        else:
            if self.state == 'budget_approved':
                 return self.action_store_process()
            raise UserError(_("No further processing step for the current state."))
    
    def action_store_process(self):
        """Logic for Store Step: Branch to SIV or PR based on stock"""
        self.ensure_one()
        self._compute_stock_availability()

        if self.has_available_stock:
            # All items available, auto-populate issued_qty and create SIV
            for line in self.line_ids:
                line.issued_qty = line.quantity - line.qty_transferred
            return self.action_create_siv(skip_wizard=True)
        elif self.has_shortage:
            # All items out of stock, create PR (handled in override if local purchase module installed)
            return self.action_create_pr()
        else:
            # Partial stock, open wizard
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'store.requisition.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_requisition_id': self.id},
            }

    def action_create_pr(self):
        self.ensure_one()
        raise UserError(_("Items are out of stock and no procurement module is installed to create a Purchase Request."))


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
            'submitted': 'procurement_store_requisition.group_store_requisition_verifier',
            'verified': 'procurement_store_requisition.group_store_requisition_budget_manager',
            'budget_approved': 'procurement_store_requisition.group_store_requisition_manager',
            'processed': 'base.group_user', # Requester is notified by SIV update but we can add more logic here
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
                summary=_("Requisition Approval Required"),
                note=_("A %s requisition (%s) is awaiting your action.") % (self.request_type, self.name)
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
        self.message_post(body=_(self._description + "reset to draft by %s" % self.env.user.name))
        self._notify_next_approver('draft')

    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)
    # @api.depends('approval_request_id', 'approval_request_id.approver_ids', 'state')
    # def _compute_can_approve(self):
    #     uid = self.env.user.id
    #     for rec in self:
    #         rec.can_approve = rec.state == 'pending' and uid in rec.approval_request_id.approver_ids.ids

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pickings',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
            'context': {'default_store_requisition_id': self.id},
        }
    has_available_stock = fields.Boolean(
        compute='_compute_stock_availability',
        store=True
    )
    has_partial_stock = fields.Boolean(
        compute='_compute_stock_availability',
        store=True
    )

    has_shortage = fields.Boolean(
        compute='_compute_stock_availability',
        store=True
    )

    @api.depends('line_ids.qty_on_hand', 'line_ids.quantity', 'line_ids.qty_transferred')
    def _compute_stock_availability(self):
        for rec in self:
            if not rec.line_ids:
                rec.has_available_stock = False
                rec.has_partial_stock = False
                rec.has_shortage = False
                continue

            statuses = [l.stock_status for l in rec.line_ids]

            if all(s == 'available' for s in statuses):
                rec.has_available_stock = True
                rec.has_partial_stock = False
                rec.has_shortage = False
            elif all(s == 'shortage' for s in statuses):
                rec.has_available_stock = False
                rec.has_partial_stock = False
                rec.has_shortage = True
            else:
                # Mix of available/shortage, or any partial
                rec.has_available_stock = False
                rec.has_partial_stock = True
                rec.has_shortage = False
    # @api.depends('approval_request_id')
    # def _compute_step_progress(self):
    #     for rec in self:
    #         rec.step_progress = rec.approval_request_id.step_progress if rec.approval_request_id else "<span>No approval steps yet.</span>"
    def action_create_siv(self, skip_wizard=False):
        self.ensure_one()
        self._compute_stock_availability()
        if not self.warehouse_id:
            raise exceptions.ValidationError("Please select a Source Warehouse first.")
        
        # Check if we have partial stock scenario - open wizard
        if self.has_partial_stock and not skip_wizard:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'store.requisition.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_requisition_id': self.id},
            }
        
        picking_type = self.warehouse_id.int_type_id or self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('code', '=', 'internal')
        ], limit=1)
        
        # Determine the partner for the picking.
        requester_partner = self.requested_by.partner_id
        if not requester_partner:
            # Fallback to the user who created the record if no partner is linked to the employee
            requester_partner = self.create_uid.partner_id

        # property_stock_customer is company-dependent; safely get its id to avoid errors
        # when the partner doesn't have the property configured for the current company.
        customer_location = requester_partner and requester_partner.with_company(
            self.company_id
        ).property_stock_customer
        dest_location_id = (
            customer_location and customer_location.id
        ) or picking_type.default_location_dest_id.id
        if not dest_location_id:
            raise exceptions.UserError(
                _("No destination location found. Please configure a Customer Location for the "
                  "partner or set a default destination on the picking type.")
            )
            
        # Only create SIV for items with manual issued_qty > 0
        move_lines = []
        for line in self.line_ids:
            if line.issued_qty <= 0:
                continue

            remaining_qty = line.quantity - line.qty_transferred
            if line.issued_qty > remaining_qty:
                raise ValidationError(_("Issued quantity for %s cannot exceed requested quantity (%s).") % (line.product_id.name, remaining_qty))

            if line.issued_qty > line.qty_on_hand:
                raise ValidationError(_("Issued quantity for %s cannot exceed available stock (%s).") % (line.product_id.name, line.qty_on_hand))
                    
            move_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.issued_qty,
                    'quantity': line.issued_qty, 
                    'product_uom': line.product_id.uom_id.id,
                    'location_id': self.location_id.id,
                    'location_dest_id': dest_location_id,
                }))
            
            # Reset issued_qty after picking creation prep
            line.issued_qty = 0

        if not move_lines:
            raise exceptions.UserError(_("No available stock to transfer or no 'Qty to Issue' was entered. Please verify item stock or enter quantities to issue."))

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': self.location_id.id,
            'location_dest_id': dest_location_id,
            'origin': self.name,
            'partner_id': requester_partner.id,
            'user_id': self.env.user.id, # Set current user as responsible (the one issuing)
            'store_requisition_id': self.id,
            'move_ids': move_lines
        }
        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()
        self.write({'state': 'waiting'})
        self.message_post(body=_(self._description + " moved to %s by %s" % (self.state.replace('_', ' ').capitalize(), self.env.user.name)))
        return self.action_view_pickings()
    def post_budget_commitments(self):
        # Now handled per-picking in StockPicking.button_validate
        pass



class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    requisition_line_id = fields.Many2one('store.requisition.line', string="Store Requisition Line")


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    store_requisition_id = fields.Many2one('store.requisition', string="Source Store Requisition")

    def button_validate(self):
        res = super().button_validate()
        AnalyticLine = self.env['account.analytic.line']
        plan_fnames = AnalyticLine._get_plan_fnames()

        for picking in self:
            requisition = picking.store_requisition_id
            if not requisition:
                continue

            # Update each line's qty_transferred based on validated moves from non-cancelled pickings
            for line in requisition.line_ids:
                line.qty_transferred = sum(
                    move.product_uom_qty
                    for p in requisition.picking_ids.filtered(lambda p: p.state != 'cancel')
                    for move in p.move_ids
                    if move.product_id == line.product_id and move.state == 'done'
                )

            # Post budget commitments immediately for the exact issued quantity
            for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                req_line = requisition.line_ids.filtered(lambda l: l.product_id == move.product_id)
                if not req_line:
                    continue
                req_line = req_line[0]
                if not req_line.budget_category_id:
                    continue
                
                issued_cost = move.product_uom_qty * req_line.unit_price
                if issued_cost <= 0:
                    continue

                vals = {
                    'name': f"{requisition.name} (SIV {picking.name}) - {req_line.product_id.name}",
                    'date': move.date.date() if getattr(move, 'date', False) else fields.Date.context_today(self),
                    'amount': -issued_cost,
                    'unit_amount': move.product_uom_qty,
                    'product_id': req_line.product_id.id,
                    'product_uom_id': req_line.uom_id.id,
                    'general_account_id': req_line.account_id.id,
                    'account_id': req_line.cost_center_id.id,
                    'requisition_line_id': req_line.id,
                    'company_id': requisition.company_id.id,
                }
                
                # In Odoo 17+, plan columns are JSON fields (analytic_distribution style).
                # They expect a dict like {str(account_id): percentage}, NOT a raw integer.
                if hasattr(req_line.cost_center_id, 'plan_id') and req_line.cost_center_id.plan_id:
                    plan_column = req_line.cost_center_id.plan_id._column_name()
                    if plan_column and plan_column != 'account_id':
                        vals[plan_column] = {str(req_line.cost_center_id.id): 100}

                AnalyticLine.create(vals)

            pickings = requisition.picking_ids
            states = pickings.mapped('state')
            fully_issued = all(line.qty_transferred >= line.quantity for line in requisition.line_ids)

            if all(s == 'cancel' for s in states):
                requisition.state = 'cancelled'
            elif fully_issued and all(s in ('done', 'cancel') for s in states):
                requisition.state = 'processed'
            else:
                pass

        return res

class StoreRequisitionLine(models.Model):
    _name = 'store.requisition.line'
    _description = 'Store Requisition Line'

    requisition_id = fields.Many2one(
        'store.requisition',
        string='Requisition',
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('type', '=', 'consu'), ('is_active_product', '=', True)]",
        required=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        store=True,
        readonly=True,
    )
    account_id = fields.Many2one('account.account', string='GL Account')

    quantity = fields.Float(
        string='Quantity',
        default=1.0
    )
    
    qty_on_hand = fields.Float(
        string='On Hand',
        compute='_compute_qty_on_hand'
    )
    
    qty_transferred = fields.Float(
        string='Issued Quantity',
        help="Quantity issued by store person, editable"
    )
    issued_qty = fields.Float(
        string='Qty to Issue',
        help="Quantity to be issued in the next SIV. Must be manually entered before clicking 'Issue'."
    )
    unit_price = fields.Float(string='Unit Price')
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center',related='requisition_id.cost_center_id',store=True)
    budget_category_id = fields.Many2one(
        'account.budget.post', 
        string='Budgetary Position',
        required=False,
        ondelete='restrict'
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
    stock_status = fields.Selection([
        ('available', 'Available'),
        ('partial', 'Partial'),
        ('shortage', 'Shortage')
    ], string='Stock Status', compute='_compute_line_stock_status')

    @api.depends('qty_on_hand', 'quantity', 'qty_transferred')
    def _compute_line_stock_status(self):
        for line in self:
            remaining_qty = line.quantity - line.qty_transferred
            if remaining_qty <= 0:
                line.stock_status = 'available'
            elif line.qty_on_hand >= remaining_qty:
                line.stock_status = 'available'
            elif line.qty_on_hand > 0:
                line.stock_status = 'partial'
            else:
                line.stock_status = 'shortage'


    state = fields.Selection(
        related='requisition_id.state',
        string='Status',
        store=True
    )
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # uom_id is a plain stored field (not related), so writing here is safe
            # and does NOT propagate to product.product.
            self.uom_id = self.product_id.uom_id
            self.unit_price = self.product_id.standard_price
            self.account_id = self.product_id.categ_id.property_account_expense_categ_id
            
    @api.depends('quantity', 'unit_price')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.quantity * line.unit_price
    
    @api.depends('product_id', 'requisition_id.warehouse_id')
    def _compute_qty_on_hand(self):
        for line in self:
            if line.product_id and line.requisition_id.warehouse_id:
                line.qty_on_hand = line.product_id.with_context(
                    warehouse=line.requisition_id.warehouse_id.id
                ).free_qty
            else:
                line.qty_on_hand = 0.0
    @api.depends('budget_category_id', 'total_price', 'cost_center_id', 'requisition_id.date_requisition', 'requisition_id.line_ids.total_price', 'requisition_id.line_ids.budget_category_id', 'requisition_id.line_ids.cost_center_id')
    def _compute_remaining_budget(self):
        for line in self:
            if line.budget_category_id and line.cost_center_id and line.requisition_id.date_requisition:
                req_date = line.requisition_id.date_requisition.date()
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
                req_date = line.requisition_id.date_requisition.date()
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
