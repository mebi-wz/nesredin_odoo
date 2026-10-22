# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetTemporaryRequest(models.Model):
    _name = 'am.asset.temporary.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Store Tool/Asset Request'
    _order = 'create_date desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('am.asset.temporary.request') or 'New',
        tracking=True
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
        string='Assets to Borrow',
        domain="[('location', '=', 'warehouse'), ('is_component', '=', False)]",
        required=True,
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Requesting Employee',
        default=lambda self: self.env.user.employee_ids[:1],
        required=True,
        tracking=True
    )

    requested_by = fields.Many2one(
        'res.users', string='Requested By',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )

    requested_date = fields.Datetime(default=lambda self: fields.Datetime.now(), readonly=True)

    return_date = fields.Date(
        string='Expected Return Date',
        required=True,
        tracking=True
    )

    note = fields.Text(string='Reason for Request')

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

    def unlink(self):
        for rec in self:
            if rec.state not in ('draft', 'cancel'):
                raise UserError(_("You can only delete draft or cancelled store requests."))
        return super().unlink()

    # ── State-Based Approval Workflow Methods ───────────────────────────────
    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft requests can be submitted."))
        if not self.asset_ids:
            raise UserError(_("Please select at least one asset to borrow."))
        if not self.employee_id:
            raise UserError(_("Please specify the requesting employee."))
        if not self.return_date:
            raise UserError(_("Please specify an expected return date."))

        self.write({
            'state': 'pending',
            'reject_reason': False,
        })
        self.message_post(
            body=_(
                "Store request submitted by %(user)s for %(employee)s. "
                "Assets: %(assets)s. Pending approval.",
                user=self.requested_by.name,
                employee=self.employee_id.name,
                assets=', '.join(self.asset_ids.mapped('name')),
            )
        )

    def action_approve(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be approved."))
        if not self.asset_ids:
            raise UserError(_("No assets selected for this store request."))
        if not self.employee_id:
            raise UserError(_("Please specify the requesting employee."))

        self._create_asset_transaction()
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_(
                "Store request approved by %(user)s and asset assignment completed.",
                user=self.env.user.name,
            )
        )

    def action_reject(self, reason=False):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be rejected."))

        vals = {
            'state': 'rejected',
            'approver_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
        }
        if reason:
            vals['reject_reason'] = reason
        self.write(vals)

        body = _("Store request rejected by %(user)s.", user=self.env.user.name)
        if reason:
            body += f"<br/><b>Reason:</b> {reason}"
        self.message_post(body=body)

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be rejected."))
        return {
            'name': _("Reject Store Request"),
            'type': 'ir.actions.act_window',
            'res_model': 'am.asset.request.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_temporary_id': self.id,
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

    def action_print_store_request(self):
        self.ensure_one()
        return self.env.ref(
            'asset_management.action_store_request_report'
        ).report_action(self)

    def _create_asset_transaction(self):
        """Generate the real asset transaction after approval (Store -> Employee)"""
        wizard = self.env['am.asset.transaction.wizard'].sudo().with_context(
            allowed_bypass_request_check=True
        ).create({
            'transaction_type': 'assign_employee',
            'asset_ids': [(6, 0, self.asset_ids.ids)],
            'employee_id': self.employee_id.id,
            'reference': f"Store Request: {self.name}",
        })
        wizard.sudo().action_confirm()
