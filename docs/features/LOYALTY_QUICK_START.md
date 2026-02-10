# Loyalty Program - Quick Start Guide

## 🎯 Get Started in 3 Minutes!

### Step 1: Create a Customer (30 seconds)
1. Go to **Customers** → **Add Customer**
2. Fill in:
   - Name: "John Doe"
   - Phone: "0712345678"
   - Email (optional)
3. Click **Save**
4. Customer starts at **Bronze tier** with **0 points**

### Step 2: Make a Sale with Customer (1 minute)
1. Go to **New Sale** (POS screen)
2. **Select Customer** from dropdown at top
   - See customer info appear (tier, current points)
3. Add products to cart (e.g., KES 1,500 worth)
4. See **"Points to Earn"** badge appear
   - Shows: 15 points (1,500 ÷ 100 × 1.0)
5. Click **Complete Sale**
6. Success message shows: "Customer earned 15 loyalty points!"

### Step 3: View Customer Points (30 seconds)
1. Go to **Customers** → Click on customer name
2. See:
   - Current Points: 15
   - Lifetime Points: 15
   - Tier: Bronze
   - Transaction history

## 🎉 That's It!

The customer now has **15 loyalty points** and will automatically earn more with each purchase!

---

## 📊 Quick Reference

### Points Earning
- **1 point per KES 100 spent**
- Calculated on final total (after discount + VAT)
- Automatic when customer is selected

### Customer Tiers

| Tier | Lifetime Points | Multiplier |
|------|----------------|------------|
| 🥉 Bronze | 0 - 1,999 | 1.0x |
| 🥈 Silver | 2,000 - 4,999 | 1.2x |
| 🥇 Gold | 5,000 - 9,999 | 1.5x |
| 💎 Platinum | 10,000+ | 2.0x |

### Example Calculations

**Bronze Customer buys KES 5,000:**
- Base: 5,000 ÷ 100 = 50 points
- Multiplier: 50 × 1.0 = **50 points**

**Silver Customer buys KES 5,000:**
- Base: 5,000 ÷ 100 = 50 points
- Multiplier: 50 × 1.2 = **60 points** (20% bonus!)

**Gold Customer buys KES 5,000:**
- Base: 5,000 ÷ 100 = 50 points
- Multiplier: 50 × 1.5 = **75 points** (50% bonus!)

**Platinum Customer buys KES 5,000:**
- Base: 5,000 ÷ 100 = 50 points
- Multiplier: 50 × 2.0 = **100 points** (100% bonus!)

---

## 🔥 Pro Tips

### Tip 1: Walk-in Customers
- Don't select a customer = No points awarded
- Perfect for one-time customers

### Tip 2: Watch Tier Upgrades
- Customer automatically upgrades when reaching threshold
- Silver at 2,000 lifetime points
- Gold at 5,000 lifetime points
- Platinum at 10,000 lifetime points

### Tip 3: Track Everything
- All transactions logged in **Django Admin**
- View customer history in **Customer Detail** page
- Check **Loyalty Transactions** for audit trail

### Tip 4: Encourage Repeat Business
- Tell customers about points earned
- Show them their tier and benefits
- Remind them of points balance

---

## 📱 At the POS

### What You'll See:

```
┌─────────────────────────────────────────┐
│ Select Customer (Optional)              │
│ [Dropdown: John Doe - 0712345678]      │
│                                         │
│ Customer Info:                          │
│ John Doe                                │
│ [BRONZE] [15 points]                    │
└─────────────────────────────────────────┘

Cart Summary:
Subtotal: KES 1,500.00
Discount: KES 0.00
VAT (16%): KES 240.00
Total: KES 1,740.00

┌─────────────────────────────────────────┐
│ ⭐ Points to Earn: 17 points           │
│ 1 point per KES 100 spent              │
└─────────────────────────────────────────┘
```

---

## 🎓 Training Your Staff

### Tell them:
1. **Always ask**: "Do you have an account with us?"
2. **If yes**: Select customer from dropdown
3. **If no**: Offer to create account (takes 30 seconds)
4. **After sale**: Tell customer how many points they earned

### Benefits to mention:
- "You earned 15 points today!"
- "You're a Bronze member - keep shopping to reach Silver!"
- "Silver members earn 20% more points!"
- "You have 150 points - that's KES 150 in discounts!"

---

## 📈 Grow Your Business

### Week 1: Setup
- Create accounts for regular customers
- Train staff on system
- Start awarding points

### Week 2: Promote
- Tell customers about loyalty program
- Display tier benefits at counter
- Encourage sign-ups

### Week 3: Engage
- Check who's close to tier upgrade
- Congratulate tier upgrades
- Track repeat purchase rate

### Month 1: Analyze
- View top customers by points
- Check tier distribution
- Measure customer retention

---

## 🆘 Quick Troubleshooting

**Q: Points not showing?**
A: Make sure you selected a customer from dropdown

**Q: Wrong points amount?**
A: Check customer's tier - higher tiers earn more points

**Q: Customer not in dropdown?**
A: Go to Customers → Add Customer first

**Q: Want to see all transactions?**
A: Django Admin → Loyalty Transactions

---

## 🚀 You're Ready!

Start rewarding your customers today and watch your repeat business grow!

**Need more details?** See `LOYALTY_PROGRAM_COMPLETE.md`
