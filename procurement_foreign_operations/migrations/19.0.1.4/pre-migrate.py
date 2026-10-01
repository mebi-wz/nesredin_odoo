def migrate(cr, version):
    if not version:
        return
    
    cr.execute("""
        UPDATE foreign_payment_request
        SET requested_by = NULL
        WHERE requested_by IS NOT NULL 
        AND NOT EXISTS (
            SELECT 1 FROM res_users WHERE res_users.id = foreign_payment_request.requested_by
        )
    """)
