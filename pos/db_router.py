"""
Database router for read replica support.
Routes read-only (reporting) queries to the replica when available.

Usage: annotate querysets with .using('replica') for explicit routing,
or the router automatically sends reads to the replica.
"""

REPLICA_MODELS = {
    # Models whose reads should go to the replica
    'sale', 'saleitem', 'purchase', 'purchaseitem',
    'stockadjustment', 'activitylog', 'loyaltytransaction',
    'supplierpayment', 'expense',
}


class ReplicaRouter:
    """
    Routes read queries for reporting-heavy models to the replica DB.
    All writes always go to default.
    """

    def db_for_read(self, model, **hints):
        if model._meta.model_name in REPLICA_MODELS:
            return 'replica'
        return 'default'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Only run migrations on the default database
        return db == 'default'
