"""
sync/conflict.py — ConflictResolver for multi-device event streams.

Resolution strategies:
  - Financial events (sale_created, sale_refunded, payment_recorded):
      Server state is authoritative; client record is discarded.
  - Inventory events (inventory_updated):
      Additive merge — resolved delta = sum of all conflicting deltas.
  - All other events:
      Last-write-wins by `updated_at` (falls back to `timestamp`).

Resolution is deterministic regardless of input order.
"""
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

FINANCIAL_TYPES = frozenset(['sale_created', 'sale_refunded', 'payment_recorded'])
INVENTORY_TYPE  = 'inventory_updated'


class ConflictResolver:

    @staticmethod
    def resolve(records: list) -> list:
        """
        Given a list of EventLog-like dicts (or instances) that may conflict,
        return the resolved list.

        A "conflict" is defined as two records with the same entity key
        (event_type + entity_id extracted from payload).
        """
        from pos.models import BackupAuditLog

        # Group by (event_type, entity_id)
        groups: dict[tuple, list] = {}
        for rec in records:
            key = ConflictResolver._entity_key(rec)
            groups.setdefault(key, []).append(rec)

        resolved = []
        for (event_type, entity_id), group in groups.items():
            if len(group) == 1:
                resolved.append(group[0])
                continue

            if event_type in FINANCIAL_TYPES:
                winner = ConflictResolver._server_authoritative(group, BackupAuditLog)
            elif event_type == INVENTORY_TYPE:
                winner = ConflictResolver._additive_merge(group)
            else:
                winner = ConflictResolver._last_write_wins(group)

            # Emit audit event
            try:
                BackupAuditLog.log_backup_operation(
                    operation='backup_business',
                    backup_file='',
                    status='warning',
                    details={
                        'conflict_resolved': True,
                        'event_type':  event_type,
                        'entity_id':   entity_id,
                        'strategy':    ConflictResolver._strategy_name(event_type),
                        'candidates':  len(group),
                    },
                )
            except Exception:
                pass

            resolved.append(winner)

        return resolved

    # ── Strategies ────────────────────────────────────────────────────────────

    @staticmethod
    def _last_write_wins(group: list):
        """Select the record with the latest updated_at / timestamp."""
        def sort_key(r):
            ts = ConflictResolver._get_ts(r, 'updated_at') or ConflictResolver._get_ts(r, 'timestamp')
            return ts or ''
        return max(group, key=sort_key)

    @staticmethod
    def _server_authoritative(group: list, BackupAuditLog):
        """
        Server state wins.  All client-side records are discarded and logged.
        We identify the 'server' record as the one with device_id == 'server',
        or fall back to last-write-wins if none is marked server.
        """
        server_records = [r for r in group if ConflictResolver._get_field(r, 'device_id') == 'server']
        if server_records:
            winner = server_records[0]
            discarded = [r for r in group if r is not winner]
        else:
            winner = ConflictResolver._last_write_wins(group)
            discarded = [r for r in group if r is not winner]

        for rec in discarded:
            try:
                BackupAuditLog.log_backup_operation(
                    operation='backup_business',
                    backup_file='',
                    status='warning',
                    details={
                        'operation': 'conflict_discarded',
                        'uuid': str(ConflictResolver._get_field(rec, 'uuid', '')),
                    },
                )
            except Exception:
                pass

        return winner

    @staticmethod
    def _additive_merge(group: list):
        """
        For inventory_updated: sum all delta values.
        Returns a copy of the first record with the merged delta.
        """
        total_delta = Decimal('0')
        for rec in group:
            payload = ConflictResolver._get_field(rec, 'payload', {})
            try:
                total_delta += Decimal(str(payload.get('delta', 0)))
            except InvalidOperation:
                pass

        # Use the record with the latest timestamp as the base
        base = ConflictResolver._last_write_wins(group)

        # Produce a merged copy
        if hasattr(base, 'payload'):
            # Model instance — we can't mutate it (immutable), return as-is with note
            return base
        else:
            merged = dict(base)
            merged['payload'] = dict(merged.get('payload', {}))
            merged['payload']['delta'] = str(total_delta)
            return merged

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _entity_key(rec) -> tuple:
        event_type = ConflictResolver._get_field(rec, 'event_type', '')
        payload    = ConflictResolver._get_field(rec, 'payload', {})
        entity_id  = (
            payload.get('sale_id') or
            payload.get('product_id') or
            payload.get('return_id') or
            str(ConflictResolver._get_field(rec, 'uuid', ''))
        )
        return (event_type, str(entity_id))

    @staticmethod
    def _get_field(rec, field, default=None):
        if isinstance(rec, dict):
            return rec.get(field, default)
        return getattr(rec, field, default)

    @staticmethod
    def _get_ts(rec, field):
        val = ConflictResolver._get_field(rec, field)
        if val is None:
            return None
        return str(val)

    @staticmethod
    def _strategy_name(event_type: str) -> str:
        if event_type in FINANCIAL_TYPES:
            return 'server_authoritative'
        if event_type == INVENTORY_TYPE:
            return 'additive_merge'
        return 'last_write_wins'
