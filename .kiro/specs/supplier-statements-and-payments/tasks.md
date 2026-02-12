# Implementation Plan: Supplier Statements and Payment Tracking

## Overview

This implementation plan breaks down the supplier statements and payment tracking feature into incremental coding tasks. Each task builds on previous work, starting with database models, then service layer, views, templates, and finally testing. The implementation follows Django best practices and integrates with the existing POS system.

## Tasks

- [ ] 1. Create database models and migrations
  - [x] 1.1 Create SupplierPayment model with all fields and methods
    - Add model to pos/models.py with payment_number auto-generation
    - Include fields: payment_number, supplier, payment_date, amount, payment_method, reference_number, notes, created_by, created_at, updated_at
    - Implement save() method for payment_number generation (PAY-YYYYMMDD-XXXX format)
    - Implement total_allocated() and unallocated_amount() methods
    - Add Meta class with ordering and indexes
    - _Requirements: 1.1, 1.2, 1.6, 10.1, 10.2_
  
  - [x] 1.2 Create PaymentAllocation model with validation
    - Add model to pos/models.py
    - Include fields: payment, purchase, amount, created_at
    - Implement clean() method with all validation rules (allocation ≤ payment, total allocations ≤ purchase)
    - Add Meta class with ordering and indexes
    - _Requirements: 7.1, 7.2, 9.3, 9.4_
  
  - [x] 1.3 Extend Supplier model with payment-related methods
    - Add outstanding_balance() method (received purchases - payments)
    - Add total_payments() method
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  
  - [x] 1.4 Extend Purchase model with allocation-related methods
    - Add total_allocated() method
    - Add remaining_balance() method
    - Add is_fully_paid() method
    - Add days_outstanding() method
    - Add aging_category() method (current, 30, 60, 90+)
    - _Requirements: 6.1, 6.2, 6.6, 6.7, 7.3, 7.4, 7.5_
  
  - [x] 1.5 Create and run database migrations
    - Generate migrations for new models
    - Run migrations to create database tables
    - Verify indexes are created
    - _Requirements: All model requirements_

- [ ] 2. Implement service layer for business logic
  - [x] 2.1 Create SupplierPaymentService class
    - Create new file pos/services.py (or add to existing services file)
    - Implement create_payment() static method with @transaction.atomic
    - Include all validation (supplier active, payment method active, amount > 0)
    - Handle optional allocations parameter
    - Log activity using ActivityLog.log_activity()
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 9.1, 9.2, 9.5, 10.1, 10.3_
  
  - [x] 2.2 Implement auto-allocation FIFO logic
    - Add _auto_allocate_payment() static method to SupplierPaymentService
    - Query unpaid purchases ordered by date (oldest first)
    - Allocate payment to purchases until payment is fully allocated
    - Use annotate() and F() for efficient queries
    - _Requirements: 7.6_
  
  - [x] 2.3 Create SupplierStatementService class
    - Add to pos/services.py
    - Implement generate_statement() static method
    - Calculate opening balance (transactions before start_date)
    - Query purchases and payments in date range
    - Combine and sort transactions chronologically
    - Calculate running balance for each transaction
    - Return dict with all statement data
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  
  - [x] 2.4 Implement aging analysis service method
    - Add generate_aging_analysis() static method to SupplierStatementService
    - Query suppliers with outstanding balances
    - For each supplier, categorize unpaid purchases by age
    - Calculate amounts for current, 30, 60, 90+ day buckets
    - Return list of dicts with aging data per supplier
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 3. Create forms for payment management
  - [ ] 3.1 Create SupplierPaymentForm
    - Create pos/forms.py or add to existing forms file
    - Define ModelForm for SupplierPayment
    - Configure widgets (date picker, number input with step 0.01)
    - Add __init__ method to accept supplier parameter
    - Validate supplier is active
    - _Requirements: 1.1, 1.4, 9.1_
  
  - [ ] 3.2 Create PaymentAllocationFormSet
    - Use inlineformset_factory for PaymentAllocation
    - Configure fields (purchase, amount)
    - Set extra=3, can_delete=True
    - Add widgets for amount input
    - _Requirements: 1.5, 7.1, 7.2_

- [ ] 4. Implement views for payment management
  - [x] 4.1 Create supplier_payments view (list payments)
    - Add view function to pos/views.py
    - Query payments for supplier ordered by date (newest first)
    - Calculate total payments
    - Render payment_list.html template
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  
  - [x] 4.2 Create create_payment view (form handling)
    - Add view function with GET and POST handling
    - Display SupplierPaymentForm and PaymentAllocationFormSet
    - On POST, validate forms and call SupplierPaymentService.create_payment()
    - Handle validation errors and display messages
    - Redirect to supplier_payments on success
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  
  - [x] 4.3 Create payment_detail view
    - Display payment details with all fields
    - Show allocations with purchase references
    - Display audit information (created_by, created_at, updated_at)
    - _Requirements: 7.5, 10.4_
  
  - [x] 4.4 Create delete_payment view
    - Require DELETE permission
    - Use @transaction.atomic for deletion
    - Log deletion with ActivityLog
    - Recalculate supplier balance (automatic via model methods)
    - Redirect with success message
    - _Requirements: 9.6, 10.3_
  
  - [x] 4.5 Add date range filtering to payment history
    - Extend supplier_payments view with start_date and end_date parameters
    - Filter payments by date range if provided
    - Update template with date filter form
    - _Requirements: 4.5_

- [ ] 5. Implement views for statements and aging
  - [x] 5.1 Create supplier_statement view
    - Add view function that calls SupplierStatementService.generate_statement()
    - Accept start_date and end_date parameters (optional)
    - Pass statement data to template
    - Render statement.html
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  
  - [ ] 5.2 Create supplier_statement_print view
    - Similar to supplier_statement but render statement_print.html
    - Use print-optimized template (hide navigation, print CSS)
    - _Requirements: 5.1, 5.5_
  
  - [ ] 5.3 Create supplier_statement_pdf view
    - Install WeasyPrint library
    - Render statement_pdf.html template
    - Convert HTML to PDF using WeasyPrint
    - Return PDF as file download response
    - Handle PDF generation errors gracefully
    - _Requirements: 5.2, 5.3, 5.4_
  
  - [x] 5.4 Create aging_analysis view
    - Call SupplierStatementService.generate_aging_analysis()
    - Accept as_of_date parameter (optional, defaults to today)
    - Calculate totals across all suppliers
    - Render aging_analysis.html template
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  
  - [x] 5.5 Create supplier_balances view (supplier list with balances)
    - Query all suppliers with annotations for outstanding_balance
    - Implement sorting (by name or balance)
    - Implement filtering (only suppliers with balance > 0)
    - Calculate total outstanding across all suppliers
    - Render balance_list.html template
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 6. Create URL patterns
  - [x] 6.1 Add URL patterns to pos/urls.py
    - Add all payment management URLs (list, create, detail, delete)
    - Add statement URLs (view, print, pdf)
    - Add aging analysis URL
    - Add supplier balances URL
    - Use appropriate URL naming conventions
    - _Requirements: All view requirements_

- [ ] 7. Create templates for payment management
  - [x] 7.1 Create payment_list.html template
    - Display table of payments with date, amount, method, reference
    - Show total payments
    - Add "Create Payment" button
    - Include date range filter form
    - Extend base.html template
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 7.2 Create payment_form.html template
    - Render SupplierPaymentForm
    - Render PaymentAllocationFormSet with dynamic add/remove
    - Show unpaid purchases for supplier with remaining balances
    - Include JavaScript for formset management
    - Add form validation and error display
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  
  - [ ] 7.3 Create payment_detail.html template
    - Display all payment fields
    - Show allocations table with purchase references and amounts
    - Display audit information (created by, dates)
    - Add "Delete" button with confirmation
    - _Requirements: 7.5, 10.4_

- [ ] 8. Create templates for statements and aging
  - [ ] 8.1 Create statement.html template
    - Display business and supplier details in header
    - Show statement period and opening balance
    - Render transactions table (date, reference, description, debit, credit, balance)
    - Show closing balance and totals
    - Add "Print" and "Download PDF" buttons
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  
  - [ ] 8.2 Create statement_print.html template
    - Similar to statement.html but optimized for printing
    - Include print-specific CSS (hide buttons, optimize layout)
    - Use @media print rules
    - _Requirements: 5.1, 5.5_
  
  - [ ] 8.3 Create statement_pdf.html template
    - PDF-optimized layout with WeasyPrint CSS
    - Include @page rules for headers/footers
    - Professional formatting with proper spacing
    - Page break handling for long statements
    - _Requirements: 5.2, 5.3, 5.4_
  
  - [ ] 8.4 Create aging_analysis.html template
    - Display aging table with suppliers as rows
    - Columns: Supplier, Current, 30 Days, 60 Days, 90+ Days, Total
    - Show totals row at bottom
    - Add as_of_date selector
    - Include export/print options
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  
  - [ ] 8.5 Create balance_list.html template
    - Display supplier table with name and outstanding balance
    - Add sorting controls (by name or balance)
    - Add filter toggle (show all / only with balance)
    - Show total outstanding balance
    - Link each supplier to statement page
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Add navigation and integration
  - [x] 9.1 Update supplier detail page
    - Add "Payments" tab or section
    - Add "View Statement" button
    - Display current outstanding balance prominently
    - Link to create payment form
    - _Requirements: 2.4, 8.5_
  
  - [ ] 9.2 Update main navigation
    - Add "Supplier Payments" menu item
    - Add "Aging Analysis" menu item under Reports
    - Add "Supplier Balances" menu item
    - _Requirements: Navigation requirements_
  
  - [ ] 9.3 Update dashboard with payment summary
    - Add widget showing total outstanding to suppliers
    - Add widget showing overdue amounts (90+ days)
    - Link to aging analysis
    - _Requirements: 8.4_

- [ ] 10. Implement permissions and security
  - [ ] 10.1 Add permission checks to views
    - Use @permission_required decorator on all views
    - Check add_supplierpayment for create_payment
    - Check view_supplierpayment for payment views
    - Check delete_supplierpayment for delete_payment
    - Check view_supplier for statements
    - _Requirements: Security requirements_
  
  - [x] 10.2 Update admin interface
    - Register SupplierPayment in admin.py
    - Register PaymentAllocation as inline
    - Configure list_display, list_filter, search_fields
    - Add readonly_fields for audit fields
    - _Requirements: 10.4_

- [ ] 11. Add data validation and error handling
  - [ ] 11.1 Implement comprehensive form validation
    - Validate date ranges (start ≤ end)
    - Validate allocation amounts against purchase balances
    - Display user-friendly error messages
    - _Requirements: 9.3, 9.4_
  
  - [ ] 11.2 Add error handling for PDF generation
    - Wrap PDF generation in try-except
    - Log errors with details
    - Display user-friendly error message
    - Provide fallback to print view
    - _Requirements: 5.2_
  
  - [ ] 11.3 Implement purchase deletion protection
    - Override Purchase.delete() method or use pre_delete signal
    - Check for payment_allocations
    - Raise ProtectedError if allocations exist
    - Display informative error message in UI
    - _Requirements: 9.7_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Manually test payment creation with and without allocations
  - Verify statement generation with various date ranges
  - Test aging analysis with different data scenarios
  - Verify PDF generation works
  - Check all validations are working
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 13. Write property-based tests for core properties
  - [ ]* 13.1 Write property test for payment data persistence
    - **Property 1: Payment Data Persistence**
    - **Validates: Requirements 1.1, 1.2, 1.6**
  
  - [ ]* 13.2 Write property test for outstanding balance calculation
    - **Property 2: Outstanding Balance Calculation**
    - **Validates: Requirements 2.1, 2.5**
  
  - [ ]* 13.3 Write property test for payment reduces balance
    - **Property 3: Payment Reduces Balance**
    - **Validates: Requirements 1.3, 2.2, 2.3, 2.4**
  
  - [ ]* 13.4 Write property test for invalid payment rejection
    - **Property 4: Invalid Payment Rejection**
    - **Validates: Requirements 1.4**
  
  - [ ]* 13.5 Write property test for payment allocation recording
    - **Property 5: Payment Allocation Recording**
    - **Validates: Requirements 1.5, 7.1, 7.2**
  
  - [ ]* 13.6 Write property test for statement transaction filtering
    - **Property 6: Statement Transaction Filtering**
    - **Validates: Requirements 3.1, 3.2**
  
  - [ ]* 13.7 Write property test for statement chronological ordering
    - **Property 7: Statement Chronological Ordering**
    - **Validates: Requirements 3.3**
  
  - [ ]* 13.8 Write property test for running balance calculation
    - **Property 8: Running Balance Calculation**
    - **Validates: Requirements 3.4**
  
  - [ ]* 13.9 Write property test for FIFO auto-allocation
    - **Property 23: FIFO Auto-Allocation**
    - **Validates: Requirements 7.6**
  
  - [ ]* 13.10 Write property test for aging category assignment
    - **Property 17: Aging Category Assignment**
    - **Validates: Requirements 6.1, 6.2**
  
  - [ ]* 13.11 Write property test for allocation validation
    - **Property 30: Allocation Amount Validation**
    - **Property 31: Purchase Over-Allocation Prevention**
    - **Validates: Requirements 9.3, 9.4**

- [ ]* 14. Write unit tests for models
  - [ ]* 14.1 Write unit tests for SupplierPayment model
    - Test payment_number generation
    - Test total_allocated() and unallocated_amount() methods
    - Test edge cases (no allocations, partial allocation)
    - _Requirements: 1.1, 1.6_
  
  - [ ]* 14.2 Write unit tests for PaymentAllocation model
    - Test clean() validation for all scenarios
    - Test allocation exceeding payment amount
    - Test allocation exceeding purchase total
    - Test multiple allocations totaling more than payment
    - _Requirements: 9.3, 9.4_
  
  - [ ]* 14.3 Write unit tests for extended Supplier methods
    - Test outstanding_balance() with various scenarios
    - Test total_payments() calculation
    - Test with no purchases, no payments, mixed scenarios
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  
  - [ ]* 14.4 Write unit tests for extended Purchase methods
    - Test remaining_balance() calculation
    - Test is_fully_paid() logic
    - Test days_outstanding() calculation
    - Test aging_category() for all buckets
    - _Requirements: 6.1, 6.2, 6.6, 6.7, 7.3, 7.4, 7.5_

- [ ]* 15. Write unit tests for services
  - [ ]* 15.1 Write unit tests for SupplierPaymentService.create_payment()
    - Test successful payment creation
    - Test with explicit allocations
    - Test validation errors (inactive supplier, inactive payment method, negative amount)
    - Test transaction rollback on error
    - Test activity logging
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 9.1, 9.2, 9.5, 10.1, 10.3_
  
  - [ ]* 15.2 Write unit tests for auto-allocation FIFO logic
    - Test allocation to single purchase
    - Test allocation across multiple purchases
    - Test partial allocation when payment < total outstanding
    - Test with no unpaid purchases
    - _Requirements: 7.6_
  
  - [ ]* 15.3 Write unit tests for SupplierStatementService.generate_statement()
    - Test with empty date range (no transactions)
    - Test with single purchase
    - Test with mixed purchases and payments
    - Test opening and closing balance calculations
    - Test running balance accuracy
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  
  - [ ]* 15.4 Write unit tests for aging analysis
    - Test with no outstanding balances
    - Test with purchases in different aging buckets
    - Test with partially paid purchases
    - Test with fully paid purchases (should be excluded)
    - Test aggregation accuracy
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ]* 16. Write unit tests for views
  - [ ]* 16.1 Write unit tests for payment views
    - Test supplier_payments view (GET)
    - Test create_payment view (GET and POST)
    - Test payment_detail view
    - Test delete_payment view
    - Test permission requirements
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [ ]* 16.2 Write unit tests for statement views
    - Test supplier_statement view with date filters
    - Test supplier_statement_print view
    - Test supplier_statement_pdf view (mock PDF generation)
    - _Requirements: 3.1, 3.2, 5.1, 5.2, 5.5_
  
  - [ ]* 16.3 Write unit tests for aging and balance views
    - Test aging_analysis view
    - Test supplier_balances view with sorting
    - Test supplier_balances view with filtering
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.4_

- [ ]* 17. Write integration tests
  - [ ]* 17.1 Write integration test for complete payment workflow
    - Create supplier and purchases
    - Create payment with allocations
    - Verify balance updates
    - Verify allocations are recorded
    - Verify activity log entries
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 2.3, 7.1, 7.2, 10.1, 10.3_
  
  - [ ]* 17.2 Write integration test for statement generation
    - Create supplier with multiple purchases and payments
    - Generate statement
    - Verify all transactions appear
    - Verify balances are correct
    - Verify chronological ordering
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  
  - [ ]* 17.3 Write integration test for aging analysis
    - Create multiple suppliers with purchases of different ages
    - Create partial payments
    - Generate aging analysis
    - Verify categorization is correct
    - Verify amounts are accurate
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7_
  
  - [ ]* 17.4 Write integration test for payment deletion
    - Create payment with allocations
    - Delete payment
    - Verify balance is recalculated
    - Verify allocations are removed
    - Verify activity log entry
    - _Requirements: 9.6, 10.3_

- [ ] 18. Final checkpoint - Complete testing and documentation
  - Run all tests (unit, property, integration)
  - Fix any failing tests
  - Verify all requirements are met
  - Test in browser with realistic data
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property-based tests use Hypothesis library with minimum 100 iterations
- Service layer uses @transaction.atomic for data integrity
- All monetary calculations use Decimal type to avoid rounding errors
- PDF generation uses WeasyPrint library
- Activity logging tracks all payment operations
- Permissions are enforced on all views
