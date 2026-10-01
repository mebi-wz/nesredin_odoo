def migrate(cr, version):
    if not version:
        return
    
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Populate the new department_id column based on requested_by (res.users)
    try:
        requisitions = env['procurement.currency.request'].search([('department_id', '=', False)])
        for req in requisitions:
            employee = False
            if hasattr(req.requested_by, 'employee_id') and req.requested_by.employee_id:
                employee = req.requested_by.employee_id
            elif hasattr(req.requested_by, 'employee_ids') and req.requested_by.employee_ids:
                employee = req.requested_by.employee_ids[0]
                
            if employee and hasattr(employee, 'department_id') and employee.department_id:
                cr.execute(
                    "UPDATE procurement_currency_request SET department_id = %s WHERE id = %s",
                    (employee.department_id.id, req.id)
                )
    except Exception as e:
        pass # Ignore if any ORM failure occurs
