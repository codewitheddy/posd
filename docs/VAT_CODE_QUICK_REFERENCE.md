# VAT Code Module - Quick Reference

## At a Glance

| Feature | Details |
|---------|---------|
| **Model** | `pos.VATCode` |
| **Admin** | `/admin/pos/vatcode/` |
| **API** | `GET/POST /api/vat-codes/` |
| **Multi-Tenancy** | ✅ Per-business isolation |
| **Audit Trail** | ✅ Created/updated timestamps |
| **Migration** | `0099_add_vat_code_system` |

---

## Core Fields

```python
VATCode:
  business           # FK to Business (required)
  code               # Unique identifier, max 20 chars (required)
  name               # Display name, max 100 chars (required)
  vat_rate           # Decimal 0-100, default 16.00 (required)
  excise_rate        # Decimal 0-100, default 0.00
  import_duty        # Decimal 0-100, default 0.00
  is_excisable       # Boolean, default False
  hs_code_chapter    # String max 2 chars, nullable (optional)
  description        # Text field (optional)
  is_active          # Boolean, default True
  created_at         # Timestamp (auto)
  updated_at         # Timestamp (auto)
```

---

## API Quick Commands

### List All VAT Codes
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/vat-codes/
```

### Create VAT Code
```bash
curl -X POST http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"VAT-STD","name":"Standard","vat_rate":"16.00"}'
```

### Get Specific VAT Code
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/vat-codes/1/
```

### Update VAT Code
```bash
curl -X PATCH http://localhost:8000/api/vat-codes/1/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vat_rate":"18.00"}'
```

### Delete VAT Code
```bash
curl -X DELETE http://localhost:8000/api/vat-codes/1/ \
  -H "Authorization: Bearer TOKEN"
```

### Filter by Rate
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/vat-codes/by_rate/?rate=0.00
```

### Get Excisable Codes
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/vat-codes/excisable/
```

### Get Products Using VAT Code
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/api/vat-codes/1/products/
```

---

## Admin Shortcuts

| Action | Path |
|--------|------|
| View All | `/admin/pos/vatcode/` |
| Add New | `/admin/pos/vatcode/add/` |
| Edit (ID=1) | `/admin/pos/vatcode/1/change/` |
| Delete (ID=1) | `/admin/pos/vatcode/1/delete/` |

---

## Common VAT Code Examples

### Kenya - Standard Rates
```
Code: VAT-STD
Name: Standard Rated (16%)
Rate: 16%
Usage: Most products and services
```

```
Code: VAT-ZERO
Name: Zero Rated (0%)
Rate: 0%
Usage: Basic foodstuffs, exported services
```

```
Code: VAT-EXEMPT
Name: Exempt (0%)
Rate: 0%
Usage: Medical services, education
```

```
Code: VAT-EXCISE
Name: Excisable (16% + 20%)
Rate: 16% (VAT) + 20% (Excise)
Usage: Alcohol, tobacco, sugary drinks
```

---

## Validation Rules

```
✓ Code must be unique per business
✓ Code max 20 characters
✓ Name is required, max 100 characters
✓ VAT Rate: 0 to 100 decimal
✓ Excise Rate: 0 to 100 decimal
✓ Import Duty: 0 to 100 decimal
✓ HS Code Chapter: max 2 characters
✗ Cannot delete if products use it
✗ Code/Name cannot be blank
```

---

## Response Format

```json
{
  "id": 1,
  "code": "VAT-STD",
  "name": "Standard Rated (16%)",
  "vat_rate": "16.00",
  "excise_rate": "0.00",
  "import_duty": "0.00",
  "total_tax_rate": 16.0,
  "is_excisable": false,
  "hs_code_chapter": null,
  "description": "Standard VAT rate for regular products",
  "is_active": true,
  "product_count": 45,
  "business_name": "My Business",
  "created_at": "2026-08-11T10:30:00Z",
  "updated_at": "2026-08-11T10:30:00Z"
}
```

---

## Filter Parameters

| Parameter | Values | Example |
|-----------|--------|---------|
| search | Any text | `?search=standard` |
| ordering | code, vat_rate, created_at | `?ordering=-vat_rate` |
| active | true, false | `?active=true` |
| rate | Decimal | `?rate=16.00` |

---

## Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 400 | Bad Request | Check JSON syntax |
| 401 | Unauthorized | Check token |
| 403 | Forbidden | Check permissions |
| 404 | Not Found | Check ID exists |
| 409 | Conflict | Code already exists |

---

## Performance Tips

1. **Use Filtering** - Always filter by active status
2. **Pagination** - API auto-paginates, use `?page=2`
3. **Search** - Use search_fields for large datasets
4. **Caching** - VAT codes are cached, clear with management command
5. **Bulk Operations** - Use API for batch updates

---

## Migration Info

```
Migration: 0099_add_vat_code_system.py
Created: August 11, 2026
Changes:
  + Create VATCode model
  + Add vat_code FK to Product model
  + Create 3 indexes for performance
  + Add unique constraint (business, code)
Status: Ready to apply
```

---

## Related Fields

**Product Model:**
- `tax_class` - Legacy field (backward compatible)
- `vat_code` - New VATCode reference (preferred)
- `hs_code_ref` - HSCode library reference

**BusinessSettings:**
- `vat_rate` - Default VAT rate for business
- `vat_enabled` - Enable/disable VAT calculations

---

## Support

- **Documentation:** `/docs/VAT_CODE_MANAGEMENT_GUIDE.md`
- **Admin:** `/admin/pos/vatcode/`
- **API Docs:** `/api/docs/`
- **Contact:** support@marid.co.ke

---

**Version:** 1.0
**Last Updated:** August 11, 2026
