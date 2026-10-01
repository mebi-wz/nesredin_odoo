def migrate(cr, version):
    if not version:
        return
    
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Populate the new department_id column based on requested_by (res.users)
    try:
        requisitions = env['local.purchase.requisition'].search([('department_id', '=', False)])
        for req in requisitions:
            employee = False
            if hasattr(req.requested_by, 'employee_id') and req.requested_by.employee_id:
                employee = req.requested_by.employee_id
            elif hasattr(req.requested_by, 'employee_ids') and req.requested_by.employee_ids:
                employee = req.requested_by.employee_ids[0]
                
            if employee and hasattr(employee, 'department_id') and employee.department_id:
                cr.execute(
                    "UPDATE local_purchase_requisition SET department_id = %s WHERE id = %s",
                    (employee.department_id.id, req.id)
                )
    except Exception as e:
        pass # Ignore if any ORM failure occurs

    try:
        payments = env['local.payment.request'].search([('department_id', '=', False)])
        for pay in payments:
            employee = False
            if hasattr(pay.requested_by, 'employee_id') and pay.requested_by.employee_id:
                employee = pay.requested_by.employee_id
            elif hasattr(pay.requested_by, 'employee_ids') and pay.requested_by.employee_ids:
                employee = pay.requested_by.employee_ids[0]
                
            if employee and hasattr(employee, 'department_id') and employee.department_id:
                cr.execute(
                    "UPDATE local_payment_request SET department_id = %s WHERE id = %s",
                    (employee.department_id.id, pay.id)
                )
    except Exception as e:
        pass
