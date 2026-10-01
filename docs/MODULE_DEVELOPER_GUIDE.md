# Platform Core Module Developer Guide

## 1. Architecture Philosophy & Fundamental Rules
The ERP Platform is engineered as a **Modular Monolith** in pure Django 4.2. Modules are self-contained business domain applications (e.g. `pos`, `hr`, `accounting`, `procurement`, `inventory`, `crm`) orchestrated by a central `core` platform backoffice.

### The 5 Architectural Laws:
1. **Unidirectional Core Dependency**:
   - `core` owns cross-cutting concerns (multi-tenancy, authorization, auditing, background jobs, document numbering, event bus, approval engine, ledger, settings store).
   - Business modules depend on `core`.
   - **`core` NEVER imports from any business module.** (Verified continuously by AST import boundary tests in `core/tests/test_import_boundaries.py`).
2. **Strict Module Encapsulation (No Sibling Imports)**:
   - Sibling modules (e.g., HR and POS) MUST NEVER directly import each other's models, views, or internal services.
   - All inter-module synchronous communication occurs strictly via versioned public `<module>/api.py` interfaces.
3. **No Cross-Module Database Foreign Keys**:
   - Cross-module relationships are decoupled using Generic Foreign Keys or integer IDs resolved via public APIs or domain events.
4. **Asynchronous Communication via Transactional Outbox**:
   - Inter-module domain events are published via `core.events.bus.publish(event_name, payload, company)` inside the database transaction.
   - Subscribers handle events idempotently and out-of-band via `python manage.py dispatch_events`.
5. **Safe Degradation (Zero-Fault Disabling)**:
   - Any module can be disabled or uninstalled dynamically with zero errors across remaining modules.

---

## 2. Standard Module Structure
When building a new module (e.g., `accounting`), use `python manage.py startmodule <module_name>`:
```
<module_name>/
├── __init__.py
├── apps.py                  # Django AppConfig
├── module.py                # ModuleManifest & Backoffice Navigation Registration
├── api.py                   # Public API Interface (ONLY file external modules can import)
├── handlers.py              # Outbox Event Subscribers
├── models.py                # Internal Domain Models (Inheriting from Core Base Models)
├── selectors.py             # Read Layer (Complex Queries & Aggregations)
├── services.py              # Write Layer (Transactional Business Logic)
├── forms.py                 # Django Forms
├── views.py                 # Pure Django Class-Based Views
├── urls.py                  # Module URL Routing
├── templates/<module_name>/ # Scoped HTML Templates (Extending core/base.html)
└── tests/                   # Module Unit & Integration Tests
```

---

## 3. Module Registration (`module.py`)
Every module declares a `manifest` in `module.py`:
```python
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard

manifest = ModuleManifest(
    key='accounting',
    name='Accounting & Ledger',
    version='1.0.0',
    description='General Ledger, Chart of Accounts, and Financial Statements',
    icon='bi bi-journal-bookmark',
    dependencies=['pos'],          # Dependent modules
    permission_prefix='accounting',
    default_roles={
        'Chief Financial Officer': ['accounting.view_all', 'accounting.post_journal'],
        'Staff Accountant': ['accounting.post_journal'],
    },
    menu_sections=[
        MenuSection(
            title='Accounting',
            order=40,
            items=[
                MenuItem(title='Dashboard', url_name='accounting:dashboard', icon='bi bi-speedometer2'),
                MenuItem(title='Journal Entries', url_name='accounting:journal_list', icon='bi bi-list-columns'),
                MenuItem(title='Trial Balance', url_name='accounting:trial_balance', icon='bi bi-file-earmark-spreadsheet'),
            ],
        ),
    ],
    dashboard_cards=[
        DashboardCard(title='Cash at Bank', template_name='accounting/cards/cash_balance.html', order=10),
    ],
    url_prefix='/accounting/',
)
```

---

## 4. Multi-Tenancy & Data Scoping
Inherit your models from Core base classes:
```python
from django.db import models
from core.models import TimeStampedModel, CompanyScopedModel, BranchScopedModel, AuditedModel

class Account(CompanyScopedModel, AuditedModel, TimeStampedModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
```
In Class-Based Views:
```python
from django.views.generic import ListView
from core.views import ModuleEnabledRequiredMixin, CompanyBranchScopeMixin

class AccountListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    module_key = 'accounting'
    model = Account
    template_name = 'accounting/account_list.html'
    context_object_name = 'accounts'
```

---

## 5. Concurrency-Safe Document Numbering
Never generate sequence numbers with `Model.objects.count() + 1` or un-locked filters. Always call:
```python
from core.numbering.service import next_document_number

invoice_number = next_document_number(
    document_type='sale_invoice',
    company=company,
    branch=branch,
    date_val=today,
    prefix='INV',
    format_pattern='{prefix}-{branch_code}-{year}{month:02d}-{seq:04d}',
)
```

---

## 6. Asynchronous Event Publishing & Subscribing
Publish inside your transactional service:
```python
from core.events.bus import publish

publish(
    event_name='pos.sale_completed.v1',
    payload={
        'sale_id': sale.pk,
        'invoice_number': sale.invoice_number,
        'total': str(sale.total),
    },
    company=company,
)
```
Subscribe in `handlers.py`:
```python
from core.events.bus import subscribe

@subscribe('pos.sale_completed.v1')
def create_ledger_entry_on_sale(event_payload: dict):
    # Idempotent handler
    pass
```

---

## 7. Accounting Public Posting Interface
To record double-entry transactions from any module:
```python
from core.accounting.api import post_journal_entry

entry = post_journal_entry(
    company=company,
    entries=[
        {'account_code': '1000', 'account_name': 'Cash in Till', 'debit': Decimal('500.00'), 'credit': Decimal('0.00')},
        {'account_code': '4000', 'account_name': 'Sales Revenue', 'debit': Decimal('0.00'), 'credit': Decimal('431.03')},
        {'account_code': '2100', 'account_name': 'VAT Output', 'debit': Decimal('0.00'), 'credit': Decimal('68.97')},
    ],
    source_module='pos',
    source_ref=sale.invoice_number,
    idempotency_key=f"pos:{sale.invoice_number}",
    narration='Daily POS Sale Transaction',
)
```

---

## 8. Multi-Level Approval Workflows
Submit approval requests for high-value transactions:
```python
from core.workflows.engine import submit_for_approval

approval_request = submit_for_approval(
    workflow_code='purchase_order_approval',
    instance=purchase_order,
    company=company,
    requester=user,
    metadata={'total_amount': str(purchase_order.total_amount)},
)
```

---

## 9. Background Jobs Queue (No Celery)
Queue asynchronous tasks in the DB-backed Job table:
```python
from core.jobs.queue import JobQueue

job = JobQueue.enqueue(
    task_name='pos.tasks.generate_z_report_pdf',
    kwargs={'report_id': report.id},
    company=company,
    priority=10,
)
```
Background workers execute jobs via:
`python manage.py run_jobs --workers 4`
Outbox events are dispatched via:
`python manage.py dispatch_events`

---

## 10. Kenya Localization & Privacy Compliance (DPA 2019)
- Currency: `KES` formatted to 2 decimal places with comma separation.
- Timezone: `Africa/Nairobi` (EAT / UTC+3).
- Counties & Banks: Seed with `python manage.py seed_kenya_reference_data`.
- Privacy Compliance:
  - Export personal data via `core.privacy.service.export_data_subject_profile(user)`.
  - Anonymize personal data via `core.privacy.service.anonymize_user_personal_data(user)`.
  - Log access to sensitive identifiers (KRA PIN, National ID) via `core.privacy.service.log_sensitive_data_access(...)`.
