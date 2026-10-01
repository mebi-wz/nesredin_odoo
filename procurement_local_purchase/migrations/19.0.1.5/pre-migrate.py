def migrate(cr, version):
    if not version:
        return
    
    # Clean up requested_by to avoid constraint errors when dropping/recreating users.
    # Since requested_by was changed from hr_employee to res_users, some old records 
    # might still hold employee IDs instead of user IDs causing validation errors.
    # We ensure that any requested_by that doesn't exist in res_users is set to NULL.
    cr.execute("""
        UPDATE local_purchase_requisition
        SET requested_by = NULL
        WHERE requested_by IS NOT NULL 
        AND NOT EXISTS (
            SELECT 1 FROM res_users WHERE res_users.id = local_purchase_requisition.requested_by
        )
    """)
    
    cr.execute("""
        UPDATE local_payment_request
        SET requested_by = NULL
        WHERE requested_by IS NOT NULL 
        AND NOT EXISTS (
            SELECT 1 FROM res_users WHERE res_users.id = local_payment_request.requested_by
        )
    """)
