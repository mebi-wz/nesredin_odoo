# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.export import CSVExport, ExcelExport

_logger = logging.getLogger(__name__)


def _record_audit_log(data, format_type):
    """Helper function to record export operations without failing the user response."""
    try:
        if not data:
            return
        params = json.loads(data)
        model_name = params.get('model')
        if not model_name or model_name not in request.env:
            return

        fields_data = params.get('fields', [])
        ids = params.get('ids', [])
        domain = params.get('domain', [])

        if ids:
            record_count = len(ids)
            export_mode = 'selected'
        else:
            Model = request.env[model_name]
            record_count = Model.search_count(domain) if hasattr(Model, 'search_count') else 0
            export_mode = 'all'

        ip_address = request.httprequest.remote_addr if request.httprequest else False
        user_agent = request.httprequest.user_agent.string if (request.httprequest and request.httprequest.user_agent) else False

        request.env['data.export.audit.log'].log_export_operation(
            user=request.env.user,
            model_name=model_name,
            record_count=record_count,
            format_type=format_type,
            fields_data=fields_data,
            domain=domain,
            export_mode=export_mode,
            ip_address=ip_address,
            user_agent=user_agent,
            status='success'
        )
    except Exception as e:
        _logger.exception("Error while logging data export audit: %s", e)


class AuditCSVExport(CSVExport):

    @http.route('/web/export/csv', type='http', auth='user')
    def web_export_csv(self, data):
        response = super().web_export_csv(data)
        _record_audit_log(data, 'csv')
        return response


class AuditExcelExport(ExcelExport):

    @http.route('/web/export/xlsx', type='http', auth='user')
    def web_export_xlsx(self, data):
        response = super().web_export_xlsx(data)
        _record_audit_log(data, 'xlsx')
        return response
