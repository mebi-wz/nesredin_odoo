# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class DataExportAuditLog(models.Model):
    _name = 'data.export.audit.log'
    _description = 'Data Export Audit Log'
    _order = 'export_time desc, id desc'
    _rec_name = 'display_name'

    user_id = fields.Many2one(
        'res.users',
        string='Exported By',
        ondelete='set null',
        index=True
    )
    user_name = fields.Char(string='User Name', readonly=True, index=True)
    user_login = fields.Char(string='User Login / Email', readonly=True, index=True)
    export_time = fields.Datetime(
        string='Export Timestamp',
        default=fields.Datetime.now,
        readonly=True,
        index=True
    )
    res_model = fields.Char(
        string='Technical Model',
        readonly=True,
        index=True,
        help="Technical name of the exported object (e.g., sale.order, res.partner)"
    )
    res_model_name = fields.Char(
        string='Data Type / Object',
        readonly=True,
        index=True,
        help="Human-readable business name (e.g. Sales Order, Contact, Product)"
    )
    export_format = fields.Selection([
        ('xlsx', 'Excel (.xlsx)'),
        ('csv', 'CSV (.csv)'),
    ], string='Format', default='xlsx', readonly=True, index=True)

    record_count = fields.Integer(
        string='Records Exported',
        default=0,
        readonly=True,
        index=True,
        help="Total number of records included in the downloaded file."
    )
    fields_count = fields.Integer(
        string='Fields Count',
        default=0,
        readonly=True
    )
    exported_fields = fields.Text(
        string='Exported Fields',
        readonly=True,
        help="Columns and field names included in the export."
    )
    export_domain = fields.Text(
        string='Filter Criteria / Domain',
        readonly=True,
        help="Active search filters applied at the moment of export."
    )
    export_mode = fields.Selection([
        ('selected', 'Selected Records'),
        ('all', 'Filtered Dataset / Export All'),
    ], string='Selection Mode', default='all', readonly=True)

    ip_address = fields.Char(string='Client IP Address', readonly=True)
    user_agent = fields.Char(string='Browser / User Agent', readonly=True)
    status = fields.Selection([
        ('success', 'Successful'),
        ('failed', 'Failed'),
    ], string='Status', default='success', readonly=True, index=True)
    display_name = fields.Char(string='Audit Summary', compute='_compute_display_name', store=True)

    @api.depends('res_model_name', 'record_count', 'export_time', 'user_name')
    def _compute_display_name(self):
        for rec in self:
            date_str = rec.export_time.strftime('%Y-%m-%d %H:%M') if rec.export_time else ''
            rec.display_name = f"{rec.user_name or 'Unknown'} exported {rec.record_count} {rec.res_model_name or rec.res_model or 'Records'} ({date_str})"

    @api.model
    def log_export_operation(self, user, model_name, record_count, format_type,
                             fields_data=None, domain=None, export_mode='all',
                             ip_address=None, user_agent=None, status='success'):
        """
        Creates an audit entry for a data export operation safely.
        """
        try:
            # Determine human-readable model name
            readable_model_name = model_name
            if model_name in self.env:
                readable_model_name = self.env[model_name]._description or model_name

            # Format fields summary
            formatted_fields = []
            if fields_data:
                for item in fields_data:
                    if isinstance(item, dict):
                        label = item.get('label') or item.get('name') or ''
                        name = item.get('name') or ''
                        formatted_fields.append(f"{label} ({name})" if label and label != name else name)
                    elif isinstance(item, str):
                        formatted_fields.append(item)

            fields_str = ", ".join(formatted_fields) if formatted_fields else ""
            domain_str = json.dumps(domain) if domain else ""

            vals = {
                'user_id': user.id if user else False,
                'user_name': user.name if user else 'Unknown',
                'user_login': user.login if user else 'Unknown',
                'export_time': fields.Datetime.now(),
                'res_model': model_name,
                'res_model_name': readable_model_name,
                'export_format': format_type,
                'record_count': record_count or 0,
                'fields_count': len(formatted_fields),
                'exported_fields': fields_str,
                'export_domain': domain_str,
                'export_mode': export_mode,
                'ip_address': ip_address or False,
                'user_agent': (user_agent or '')[:250] if user_agent else False,
                'status': status,
            }
            # Create using sudo so unprivileged users can have their exports audited without security errors
            return self.sudo().create(vals)
        except Exception as e:
            _logger.exception("Failed to write data export audit log: %s", e)
            return False
