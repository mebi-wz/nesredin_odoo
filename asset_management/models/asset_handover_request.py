# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AssetHandoverRequest(models.Model):
    _name = 'am.asset.handover.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'User Asset Handover Request'
    _order = 'create_date desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('am.asset.handover.request') or 'New',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        readonly=True,
    )

    asset_ids = fields.Many2many(
        'am.asset',
        string='Assets',
        domain="[('id', 'in', allowed_asset_ids)]",
    )

    to_employee_id = fields.Many2one(
        'hr.employee',
        string='To Employee',
        domain="[('id', 'in', allowed_employee_ids)]",
        tracking=True
    )
    to_warehouse_id = fields.Many2one('am.asset.warehouse', string='To Warehouse', tracking=True)

    allowed_asset_ids = fields.Many2many(
        'am.asset',
        compute="_compute_allowed_asset_ids",
        store=False
    )

    allowed_employee_ids = fields.Many2many(
        'hr.employee',
        compute="_compute_allowed_employee_ids",
        store=False
    )

    is_property_manager = fields.Boolean(
        compute='_compute_is_property_manager',
        store=False,
    )

    note = fields.Text(string='Reason / Remark')

    requested_by = fields.Many2one(
        'res.users', string='Requested By',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    requested_date = fields.Datetime(default=lambda self: fields.Datetime.now(), readonly=True)

    # ── State-Based Approval Workflow Fields ──────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancel', 'Cancelled'),
    ], default='draft', string='Status', readonly=True, copy=False, tracking=True)

    approver_id = fields.Many2one(
        'res.users',
        string='Reviewed By',
        readonly=True,
        copy=False,
        tracking=True,
    )
    approval_date = fields.Datetime(
        string='Review Date',
        readonly=True,
        copy=False,
        tracking=True,
    )
    reject_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        copy=False,
        tracking=True,
    )

    handover_type = fields.Selection([
        ('permanent', 'Permanent Handover'),
    ], string='Handover Type', default='permanent', required=True,
       tracking=True)

    return_date = fields.Date(
        string='Expected Return Date'
    )

    signature = fields.Binary(string='Recipient Signature', attachment=True)
    signed_by = fields.Char(string='Signed By')

    # ── Compute allowed assets ──────────────────────────────────────────────
    @api.depends('requested_by')
    def _compute_allowed_asset_ids(self):
        for rec in self:
            user = rec.requested_by or rec.env.user
            employee = user.employee_ids[:1]
            if employee:
                assets = rec.env['am.employee.asset'].search([
                    ('employee_id', '=', employee.id),
                    ('status', '=', 'active')
                ]).mapped('asset_id')
                rec.allowed_asset_ids = assets
            else:
                rec.allowed_asset_ids = False

    def _get_employees_under_manager(self, manager_employee):
        """Recursively fetch all employees under the given manager employee."""
        employees = self.env['hr.employee']
        queue = [manager_employee.id]
        visited = set()
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            reports = self.env['hr.employee'].sudo().search([('parent_id', '=', current_id)])
            for r in reports:
                employees |= r
                queue.append(r.id)
        return employees

    @api.depends('requested_by')
    def _compute_allowed_employee_ids(self):
        is_property_mgr = (
            self.env.user.has_group('asset_management.group_asset_property_manager')
            or self.env.user.has_group('asset_management.group_asset_manager')
            or self.env.user.has_group('asset_management.group_asset_ffa_expert')
        )
        for rec in self:
            if is_property_mgr:
                rec.allowed_employee_ids = self.env['hr.employee'].sudo().search([])
            else:
                user = rec.requested_by or rec.env.user
                employee = user.employee_ids[:1]
                if employee:
                    rec.allowed_employee_ids = rec._get_employees_under_manager(employee)
                else:
                    rec.allowed_employee_ids = self.env['hr.employee']

    def _compute_is_property_manager(self):
        is_mgr = (
            self.env.user.has_group('asset_management.group_asset_property_manager')
            or self.env.user.has_group('asset_management.group_asset_manager')
            or self.env.user.has_group('asset_management.group_asset_ffa_expert')
        )
        for rec in self:
            rec.is_property_manager = is_mgr

    @api.constrains('to_employee_id', 'to_warehouse_id')
    def _check_assignment_rights(self):
        is_property_mgr = (
            self.env.user.has_group('asset_management.group_asset_property_manager')
            or self.env.user.has_group('asset_management.group_asset_manager')
            or self.env.user.has_group('asset_management.group_asset_ffa_expert')
        )
        for rec in self:
            if not rec.to_employee_id and not rec.to_warehouse_id:
                continue

            user = rec.requested_by or rec.env.user
            employee = user.employee_ids[:1]
            subordinates = rec.env['hr.employee']
            if employee:
                subordinates = rec._get_employees_under_manager(employee)

            if not is_property_mgr:
                if not subordinates:
                    raise ValidationError(_(
                        "You do not have any employees under your hierarchy, and you are not a Property Manager. "
                        "Only a Property Manager can assign assets to another employee or a warehouse."
                    ))
                else:
                    if rec.to_warehouse_id:
                        raise ValidationError(_(
                            "Only a Property Manager can assign assets to a warehouse."
                        ))
                    if rec.to_employee_id and rec.to_employee_id not in subordinates:
                        raise ValidationError(_(
                            "You can only assign assets to employees under your hierarchy."
                        ))

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_("You can only delete draft or cancelled handover requests."))
        return super().unlink()

    # ── State-Based Approval Workflow Methods ───────────────────────────────
    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft requests can be submitted."))
        if not self.asset_ids:
            raise UserError(_("Please select at least one asset to hand over."))
        if not self.to_employee_id and not self.to_warehouse_id:
            raise UserError(_("Please specify an employee or warehouse recipient."))

        self.write({
            'state': 'pending',
            'reject_reason': False,
        })

        self.message_post(
            body=_(
                "Asset handover request submitted by %(user)s. "
                "Assets: %(assets)s. Pending approval.",
                user=self.requested_by.name,
                assets=', '.join(self.asset_ids.mapped('name'))
            )
        )

    def action_approve(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be approved."))
        if not self.asset_ids:
            raise UserError(_("No assets selected for handover."))
        if not self.to_employee_id and not self.to_warehouse_id:
            raise UserError(_("Please specify an employee or warehouse recipient."))

        self._create_asset_transaction()
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })

        recipient_name = (
            self.to_employee_id.name if self.to_employee_id
            else (self.to_warehouse_id.name if self.to_warehouse_id else _('Warehouse'))
        )
        self.message_post(
            body=_(
                "Asset handover approved by %(user)s and transfer completed. "
                "Assets assigned to %(recipient)s.",
                user=self.env.user.name,
                recipient=recipient_name,
            )
        )

    def action_reject(self, reason=False):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Cannot reject request in this state."))

        vals = {
            'state': 'rejected',
            'approver_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        }
        if reason:
            vals['reject_reason'] = reason
        self.write(vals)

        body = _("Asset handover request rejected by %(user)s.", user=self.env.user.name)
        if reason:
            body += f"<br/><b>Reason:</b> {reason}"
        self.message_post(body=body)

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be rejected."))
        return {
            'name': _("Reject Handover Request"),
            'type': 'ir.actions.act_window',
            'res_model': 'am.asset.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_handover_id': self.id,
            }
        }

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('rejected', 'cancel'):
                raise UserError(_("Only rejected or cancelled requests can be reset to draft."))
            rec.write({
                'state': 'draft',
                'approver_id': False,
                'approval_date': False,
                'reject_reason': False,
            })
            rec.message_post(body=_("Request reset to draft by %s.", rec.env.user.name))

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'pending'):
                raise UserError(_("Only draft or pending requests can be cancelled."))
            rec.write({'state': 'cancel'})
            rec.message_post(body=_("Request cancelled by %s.", rec.env.user.name))

    # ── Create the real asset transaction ──────────────────────────────────
    def _create_asset_transaction(self):
        """Generate the real asset transaction."""
        transaction_type = 'assign_employee' if self.to_employee_id else 'assign_warehouse'

        wizard = self.env['am.asset.transaction.wizard'].sudo().with_context(
            allowed_bypass_request_check=True
        ).create({
            'transaction_type': transaction_type,
            'asset_ids': [(6, 0, self.asset_ids.ids)],
            'employee_id': self.to_employee_id.id or False,
            'to_warehouse_id': self.to_warehouse_id.id or False,
            'reference': self.note or self.name,
        })
        try:
            wizard.sudo().action_confirm()
        except Exception as e:
            raise UserError(_("Failed to create asset transaction: %(error)s", error=str(e)))

        self.message_post(
            body=_(
                "Asset transaction created automatically for request %(ref)s. "
                "Assets: %(assets)s.",
                ref=self.name,
                assets=', '.join(self.asset_ids.mapped('name')),
            )
        )

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('asset_management.action_handover_request_report').report_action(self)
