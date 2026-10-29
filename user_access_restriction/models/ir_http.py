# -*- coding: utf-8 -*-
import logging
from odoo import models, http, _
from odoo.http import request, root

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        if request.env.uid and not request.env.user.is_public:
            cls._enforce_user_time_restriction(endpoint)

    @classmethod
    def _enforce_user_time_restriction(cls, endpoint=None):
        """
        Enforces date and time access restrictions in real-time across active sessions,
        HTTP requests, JSON-RPC calls, and alternate entry points (NSP-13.3 & NSP-13.4).
        """
        user = request.env.user
        if not user or user.is_exempt_from_access_restriction():
            return

        ip_address = request.httprequest.remote_addr if request.httprequest else False
        user_agent = request.httprequest.user_agent.string if (request.httprequest and request.httprequest.user_agent) else False

        is_allowed, reason = user.sudo().check_time_access(ip_address=ip_address, user_agent=user_agent)
        if not is_allowed:
            _logger.warning(
                "Access blocked for restricted user '%s' (ID %s). Reason: %s",
                user.login, user.id, reason
            )

            # Record in the security audit log
            try:
                request.env['user.access.audit.log'].sudo().log_blocked_attempt(
                    user=user,
                    reason=reason,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            except Exception:
                pass

            # Permanently delete the session from the server's session store (disk/cache).
            # This ensures that when the browser refreshes, it cannot reuse the old session
            # and is immediately redirected to /web/login instead of re-triggering the dialog.
            if request.session:
                try:
                    root.session_store.delete(request.session)
                except Exception:
                    pass
                request.session.logout(keep_db=True)

            # Raise SessionExpiredException to signal the frontend web client
            raise http.SessionExpiredException(reason)
