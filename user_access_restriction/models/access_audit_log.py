# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class UserAccessAuditLog(models.Model):
    _name = 'user.access.audit.log'
    _description = 'User Access Security Audit Log'
    _order = 'attempt_time desc, id desc'
    _rec_name = 'user_login'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        ondelete='set null',
        index=True
    )
    user_name = fields.Char(string='User Name', readonly=True, index=True)
    user_login = fields.Char(string='Login / Email', readonly=True, index=True)
    attempt_time = fields.Datetime(
        string='Timestamp',
        default=fields.Datetime.now,
        readonly=True,
        index=True
    )
    ip_address = fields.Char(string='IP Address', readonly=True)
    user_agent = fields.Char(string='User Agent / Browser', readonly=True)
    reason = fields.Text(string='Reason for Block', readonly=True)
    status = fields.Selection([
        ('blocked', 'Access Blocked'),
        ('allowed', 'Allowed'),
    ], string='Status', default='blocked', readonly=True, index=True)
    schedule_summary = fields.Char(
        string='Configured Schedule',
        readonly=True
    )

    @api.model
    def log_blocked_attempt(self, user, reason, ip_address=None, user_agent=None):
        """Creates an audit log entry in a safe manner."""
        try:
            # Format user schedule for immediate insight
            schedule = user.get_access_schedule_summary() if hasattr(user, 'get_access_schedule_summary') else ''
            vals = {
                'user_id': user.id if user else False,
                'user_name': user.name if user else 'Unknown',
                'user_login': user.login if user else 'Unknown',
                'attempt_time': fields.Datetime.now(),
                'ip_address': ip_address or False,
                'user_agent': (user_agent or '')[:250] if user_agent else False,
                'reason': reason,
                'status': 'blocked',
                'schedule_summary': schedule,
            }
            # Use sudo to ensure log creation cannot be blocked by permission issues
            self.sudo().create(vals)
        except Exception:
            # Never let audit logging failure block the core security rejection
            pass
