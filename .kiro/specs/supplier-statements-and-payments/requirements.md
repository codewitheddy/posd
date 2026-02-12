# Requirements Document

## Introduction

This document specifies the requirements for implementing supplier statements and payment tracking in a Django-based Point of Sale (POS) system. The feature enables businesses to track outstanding balances with suppliers, record payments, generate comprehensive statements, and analyze aging of payables. This functionality is essential for managing supplier relationships and maintaining accurate accounts payable records.

## Glossary

- **System**: The Django POS application
- **Supplier_Statement**: A comprehensive report showing all purchases and payments for a specific supplier over a period
- **Outstanding_Balance**: The total unpaid amount owed to a supplier
- **Supplier_Payment**: A record of money paid to a supplier against their outstanding balance
- **Aging_Analysis**: A breakdown of outstanding balances by time periods (current, 30 days, 60 days, 90+ days)
- **Payment_Allocation**: The process of applying a payment to specific purchase orders
- **Statement_Period**: The date range for which a statement is generated
- **Payable**: An amount owed to a supplier for received purchases

## Requirements

### Requirement 1: Supplier Payment Recording

**User Story:** As a business owner, I want to record payments made to suppliers, so that I can track what has been paid and what remains outstanding.

#### Acceptance Criteria

1. WHEN a user creates a supplier payment, THE System SHALL record the payment amount, payment date, payment method, and reference number
2. WHEN a user creates a supplier payment, THE System SHALL associate the payment with a specific supplier
3. WHEN a user creates a supplier payment with an amount greater than zero, THE System SHALL reduce the supplier's outstanding balance by the payment amount
4. WHEN a user attempts to create a supplier payment with a negative or zero amount, THE System SHALL reject the payment and display an error message
5. WHEN a user creates a supplier payment, THE System SHALL allow optional allocation to specific purchase orders
6. WHEN a user creates a supplier payment, THE System SHALL record the user who created the payment and the timestamp

### Requirement 2: Outstanding Balance Calculation

**User Story:** As a business owner, I want to see the outstanding balance for each supplier, so that I know how much money I owe.

#### Acceptance Criteria

1. THE System SHALL calculate outstanding balance as the sum of all received purchases minus the sum of all payments for a supplier
2. WHEN a purchase is marked as received, THE System SHALL increase the supplier's outstanding balance by the purchase total amount
3. WHEN a payment is recorded, THE System SHALL decrease the supplier's outstanding balance by the payment amount
4. WHEN displaying supplier information, THE System SHALL show the current outstanding balance
5. THE System SHALL calculate outstanding balance using decimal precision to avoid rounding errors

### Requirement 3: Supplier Statement Generation

**User Story:** As a business owner, I want to generate supplier statements, so that I can review all transactions with a supplier over a specific period.

#### Acceptance Criteria

1. WHEN a user requests a supplier statement, THE System SHALL display all received purchases for the supplier within the specified date range
2. WHEN a user requests a supplier statement, THE System SHALL display all payments for the supplier within the specified date range
3. WHEN generating a supplier statement, THE System SHALL show transactions in chronological order
4. WHEN generating a supplier statement, THE System SHALL display a running balance after each transaction
5. WHEN generating a supplier statement, THE System SHALL show the opening balance at the start of the period
6. WHEN generating a supplier statement, THE System SHALL show the closing balance at the end of the period
7. WHEN generating a supplier statement, THE System SHALL include supplier details (name, contact information, address)
8. WHEN generating a supplier statement, THE System SHALL include business details (name, address, contact information)

### Requirement 4: Payment History Viewing

**User Story:** As a business owner, I want to view payment history for each supplier, so that I can track when and how much I have paid.

#### Acceptance Criteria

1. WHEN a user views a supplier's payment history, THE System SHALL display all payments made to that supplier
2. WHEN displaying payment history, THE System SHALL show payment date, amount, payment method, and reference number for each payment
3. WHEN displaying payment history, THE System SHALL show payments in reverse chronological order (newest first)
4. WHEN displaying payment history, THE System SHALL show the total amount paid to the supplier
5. WHEN displaying payment history, THE System SHALL allow filtering by date range

### Requirement 5: Printable and PDF Statement Generation

**User Story:** As a business owner, I want to generate printable and PDF supplier statements, so that I can share them with suppliers or keep them for records.

#### Acceptance Criteria

1. WHEN a user requests a printable statement, THE System SHALL generate a printer-friendly HTML version with appropriate styling
2. WHEN a user requests a PDF statement, THE System SHALL generate a PDF document containing the complete statement
3. WHEN generating a printable or PDF statement, THE System SHALL include all transaction details, balances, and supplier information
4. WHEN generating a PDF statement, THE System SHALL format the document professionally with proper headers, footers, and page breaks
5. WHEN generating a printable statement, THE System SHALL hide navigation elements and optimize for printing

### Requirement 6: Aging Analysis

**User Story:** As a business owner, I want to see an aging analysis of amounts owed to suppliers, so that I can prioritize payments and manage cash flow.

#### Acceptance Criteria

1. WHEN a user views aging analysis, THE System SHALL categorize outstanding balances into current, 30 days, 60 days, and 90+ days overdue
2. WHEN calculating aging, THE System SHALL use the purchase date as the reference date for each unpaid or partially paid purchase
3. WHEN displaying aging analysis, THE System SHALL show the total amount in each aging category for each supplier
4. WHEN displaying aging analysis, THE System SHALL calculate the total outstanding across all aging categories
5. WHEN displaying aging analysis, THE System SHALL show aging for all suppliers with outstanding balances
6. WHEN a purchase is fully paid, THE System SHALL exclude it from aging analysis
7. WHEN a purchase is partially paid, THE System SHALL include only the unpaid portion in aging analysis

### Requirement 7: Payment Allocation to Purchases

**User Story:** As a business owner, I want to allocate payments to specific purchase orders, so that I can track which purchases have been paid.

#### Acceptance Criteria

1. WHEN a user allocates a payment to a purchase, THE System SHALL record the allocation amount
2. WHEN a user allocates a payment, THE System SHALL allow allocation to multiple purchase orders
3. WHEN calculating allocated amount for a purchase, THE System SHALL sum all payment allocations for that purchase
4. WHEN a purchase is fully allocated, THE System SHALL mark it as paid
5. WHEN displaying purchase information, THE System SHALL show the allocated amount and remaining balance
6. WHERE payment allocation is not specified, THE System SHALL apply payments using first-in-first-out (FIFO) method to the oldest unpaid purchases

### Requirement 8: Supplier List with Balance Summary

**User Story:** As a business owner, I want to see a list of all suppliers with their outstanding balances, so that I can quickly identify who I owe money to.

#### Acceptance Criteria

1. WHEN a user views the supplier list, THE System SHALL display each supplier's name and outstanding balance
2. WHEN displaying the supplier list, THE System SHALL allow sorting by name or outstanding balance
3. WHEN displaying the supplier list, THE System SHALL allow filtering to show only suppliers with outstanding balances
4. WHEN displaying the supplier list, THE System SHALL show the total outstanding balance across all suppliers
5. WHEN a user clicks on a supplier, THE System SHALL navigate to the supplier's detailed statement page

### Requirement 9: Data Integrity and Validation

**User Story:** As a system administrator, I want the system to maintain data integrity for financial transactions, so that records are accurate and reliable.

#### Acceptance Criteria

1. WHEN a payment is created, THE System SHALL validate that the supplier exists and is active
2. WHEN a payment is created, THE System SHALL validate that the payment method exists and is active
3. WHEN a payment allocation is created, THE System SHALL validate that the allocation amount does not exceed the payment amount
4. WHEN a payment allocation is created, THE System SHALL validate that the total allocated amount for a purchase does not exceed the purchase total
5. THE System SHALL use database transactions to ensure atomicity when creating payments and allocations
6. WHEN a payment is deleted, THE System SHALL recalculate the supplier's outstanding balance
7. IF a purchase is deleted, THEN THE System SHALL prevent deletion if payments have been allocated to it

### Requirement 10: Audit Trail

**User Story:** As a system administrator, I want to track who created or modified payment records, so that I can maintain accountability.

#### Acceptance Criteria

1. WHEN a payment is created, THE System SHALL record the user who created it and the creation timestamp
2. WHEN a payment is modified, THE System SHALL record the user who modified it and the modification timestamp
3. WHEN a payment is deleted, THE System SHALL log the deletion action with user and timestamp
4. WHEN viewing payment details, THE System SHALL display the audit information (created by, created at, modified by, modified at)
