# -*- coding: utf-8 -*-
{
    'name': 'User Access Restriction by Date & Time',
    'version': '19.0.1.0.0',
    'category': 'Administration / Security',
    'summary': 'Restrict user system access to approved date ranges, weekdays, and daily operating hours (NSP-13)',
    'description': """
User Access Restriction by Date and Time (NSP-13)
=================================================
Allows administrators to define granular access schedules for users:
* Permitted Date Ranges (valid from date to date).
* Allowed Weekdays (Monday through Sunday).
* Daily Allowed Time Windows (e.g. 08:00 to 18:00).
* Timezone-aware validation based on user local time.
* Real-time server-side enforcement across both login and active browser/RPC sessions.
* Admin recovery controls: System administrators are permanently exempt to prevent lockout.
* Security Audit Trail: Logs all blocked access attempts with IP, timestamp, and reason.
    """,
    'author': 'Skylink Technologies',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/access_audit_log_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
