# -*- coding: utf-8 -*-
import datetime
import pytz
import logging
from odoo import models, fields, api, SUPERUSER_ID, _
from odoo.exceptions import AccessDenied, ValidationError

_logger = logging.getLogger(__name__)


def _float_to_time_str(val):
    """Convert float hours (e.g. 8.5) to formatted 24h string (e.g. 08:30)."""
    if val is None:
        return "00:00"
    hours = int(val)
    minutes = int(round((val - hours) * 60))
    if minutes >= 60:
        hours += 1
        minutes = 0
    return f"{hours:02d}:{minutes:02d}"


# Standard sorted list of timezones
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]

def _tz_get(self):
    return _tzs


class ResUsers(models.Model):
    _inherit = 'res.users'

    restrict_access_time = fields.Boolean(
        string='Restrict Access Schedule',
        default=False,
        help="When enabled, this user can only log in and interact with Odoo during the configured dates and daily times."
    )

    access_date_from = fields.Date(
        string='Approved From Date',
        help="First day the user is permitted system access. Leave blank if no start constraint."
    )

    access_date_to = fields.Date(
        string='Approved To Date',
        help="Last day the user is permitted system access. Leave blank if no expiration."
    )

    access_tz = fields.Selection(
        _tz_get,
        string='Access Timezone',
        default=lambda self: self.env.user.tz or 'Africa/Addis_Ababa',
        help="Timezone evaluated for the user's operating hours."
    )

    # Allowed Days of Week
    access_mon = fields.Boolean(string='Monday', default=True)
    access_tue = fields.Boolean(string='Tuesday', default=True)
    access_wed = fields.Boolean(string='Wednesday', default=True)
    access_thu = fields.Boolean(string='Thursday', default=True)
    access_fri = fields.Boolean(string='Friday', default=True)
    access_sat = fields.Boolean(string='Saturday', default=False)
    access_sun = fields.Boolean(string='Sunday', default=False)

    # Daily Permitted Window
    access_time_from = fields.Float(
        string='Daily Start Time',
        default=8.0,
        help="Start time in 24-hour format (e.g., 8.0 = 08:00 AM, 8.5 = 08:30 AM)."
    )

    access_time_to = fields.Float(
        string='Daily End Time',
        default=18.0,
        help="End time in 24-hour format (e.g., 18.0 = 06:00 PM, 17.5 = 05:30 PM)."
    )

    bypass_time_restriction = fields.Boolean(
        string='Emergency Access Bypass',
        default=False,
        groups="base.group_system",
        help="Administrator override to temporarily exempt this user from schedule restrictions."
    )

    @api.constrains('access_date_from', 'access_date_to')
    def _check_date_range(self):
        for user in self:
            if user.access_date_from and user.access_date_to:
                if user.access_date_from > user.access_date_to:
                    raise ValidationError(_("The 'Approved From Date' cannot be later than the 'Approved To Date'."))

    @api.constrains('access_time_from', 'access_time_to')
    def _check_time_range(self):
        for user in self:
            if user.access_time_from < 0.0 or user.access_time_from >= 24.0:
                raise ValidationError(_("Daily Start Time must be between 00:00 (0.0) and 23:59 (23.99)."))
            if user.access_time_to < 0.0 or user.access_time_to > 24.0:
                raise ValidationError(_("Daily End Time must be between 00:00 (0.0) and 24:00 (24.0)."))

    def is_exempt_from_access_restriction(self):
        """Hardened exemption logic to protect against accidental administrator lockout (NSP-13.5)."""
        self.ensure_one()
        # 1. Root / Superuser
        if self.id in (SUPERUSER_ID, 1):
            return True
        root_user = self.env.ref('base.user_root', raise_if_not_found=False)
        if root_user and self.id == root_user.id:
            return True
        # 2. Main Admin
        admin_user = self.env.ref('base.user_admin', raise_if_not_found=False)
        if admin_user and self.id == admin_user.id:
            return True
        # 3. Any System Administrator with Settings permissions
        if self.has_group('base.group_system'):
            return True
        # 4. Emergency Bypass flag
        if self.bypass_time_restriction:
            return True
        return False

    def get_access_schedule_summary(self):
        """Returns a human-readable summary of the configured schedule."""
        self.ensure_one()
        if not self.restrict_access_time:
            return _("No Restrictions (24/7 Access)")

        days = []
        if self.access_mon: days.append("Mon")
        if self.access_tue: days.append("Tue")
        if self.access_wed: days.append("Wed")
        if self.access_thu: days.append("Thu")
        if self.access_fri: days.append("Fri")
        if self.access_sat: days.append("Sat")
        if self.access_sun: days.append("Sun")
        days_str = ", ".join(days) if days else "No days allowed"

        time_str = f"{_float_to_time_str(self.access_time_from)} - {_float_to_time_str(self.access_time_to)} ({self.access_tz or 'UTC'})"
        
        date_parts = []
        if self.access_date_from:
            date_parts.append(f"From {self.access_date_from}")
        if self.access_date_to:
            date_parts.append(f"To {self.access_date_to}")
        date_str = f" | {' '.join(date_parts)}" if date_parts else ""

        return f"{days_str} | {time_str}{date_str}"

    def check_time_access(self, ip_address=None, user_agent=None):
        """
        Validates if this user is allowed to access the system right now.
        Returns: (is_allowed: bool, reason: str or None)
        """
        self.ensure_one()
        if not self.restrict_access_time or self.is_exempt_from_access_restriction():
            return True, None

        # Determine user local time
        user_tz_name = self.access_tz or self.tz or self.company_id.partner_id.tz or 'UTC'
        try:
            user_tz = pytz.timezone(user_tz_name)
        except Exception:
            user_tz = pytz.utc

        now_utc = datetime.datetime.now(pytz.utc)
        now_local = now_utc.astimezone(user_tz)
        today_date = now_local.date()

        # 1. Date Range Check
        if self.access_date_from and today_date < self.access_date_from:
            reason = _("Your access is not yet active. Permitted starting from %s (Your local date: %s).") % (
                self.access_date_from, today_date
            )
            return False, reason

        if self.access_date_to and today_date > self.access_date_to:
            reason = _("Your approved access period expired on %s (Your local date: %s).") % (
                self.access_date_to, today_date
            )
            return False, reason

        # 2. Weekday Check
        weekday_num = now_local.weekday()
        weekday_names = [_('Monday'), _('Tuesday'), _('Wednesday'), _('Thursday'), _('Friday'), _('Saturday'), _('Sunday')]
        day_allowed_map = {
            0: self.access_mon,
            1: self.access_tue,
            2: self.access_wed,
            3: self.access_thu,
            4: self.access_fri,
            5: self.access_sat,
            6: self.access_sun,
        }
        if not day_allowed_map.get(weekday_num, False):
            reason = _("Access is not permitted on %ss. Allowed days: %s.") % (
                weekday_names[weekday_num],
                self.get_access_schedule_summary()
            )
            return False, reason

        # 3. Daily Time Window Check
        current_time_float = now_local.hour + (now_local.minute / 60.0) + (now_local.second / 3600.0)
        from_time = self.access_time_from
        to_time = self.access_time_to

        is_within_hours = False
        if from_time <= to_time:
            # Standard single-day window (e.g. 08:00 to 18:00)
            if from_time <= current_time_float <= to_time:
                is_within_hours = True
        else:
            # Overnight window (e.g. 22:00 to 06:00)
            if current_time_float >= from_time or current_time_float <= to_time:
                is_within_hours = True

        if not is_within_hours:
            current_formatted = now_local.strftime('%H:%M')
            from_formatted = _float_to_time_str(from_time)
            to_formatted = _float_to_time_str(to_time)
            reason = _("Access is only permitted between %s and %s (%s). Current local time is %s.") % (
                from_formatted, to_formatted, user_tz_name, current_formatted
            )
            return False, reason

        return True, None

    def _check_credentials(self, password, env):
        """Intercept login credentials verification to block unauthorized login attempts (NSP-13.4)."""
        res = super()._check_credentials(password, env)
        is_allowed, reason = self.sudo().check_time_access()
        if not is_allowed:
            _logger.warning("Blocked login attempt for user '%s' (%s): %s", self.login, self.id, reason)
            self.env['user.access.audit.log'].log_blocked_attempt(
                user=self,
                reason=reason,
                ip_address=self.env.context.get('remote_addr') or False
            )
            raise AccessDenied(reason)
        return res
