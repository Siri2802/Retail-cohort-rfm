# Raw data profile notes

## Q1 Shape
rows: 1067371
invoices: 53628
customers: 5942
stock_codes: 5304
countries: 43
first date: 2009-12-01 07:45:00
last date:  2011-12-09 12:50:00

Note: last date is 2011-12-09 - December 2011 has only 9 days of data.
A partial month will look like a sudden drop in monthly cohorts; must be
handled (excluded or flagged) in the cohort analysis.

## Q2 Nulls
null customer_id: 243007 (22.77%)
null description: 4382 ( 0.41%)

Meaning: 22.77% of rows have no customer ID. They are real sales but can't
be linked to a customer, so they can't be used in cohort retention or RFM.
Exclude from customer-level analysis only, and log in the exclusion ledger.

## Q3 Negative quantity
rows: 22950(2.15%)

Guess: returns/cancellations. Q5 showed this is only partly true -
3,457 of these are warehouse write-offs, not customer returns.

## Q4 Cancellation invoices (C prefix)
rows: 19494
invoices: 8292

## Q5 C-invoice vs negative quantity

## 5 Part1 table:
- normal sale (not C, not negative):        1044420 rows
- negative but NOT C-invoice:               3457 rows
- C-invoice but NOT negative:               1 rows
- normal cancellation (C and negative):     19493 rows
Check: sums to 1,067,371 total; 3,457 + 19,493 = 22,950 (matches Q3).

## 5 Part2 - negative quantity but NOT a C-invoice (sample of 30)
All sampled rows have unit_price = 0 and customer_id = NULL.
Descriptions are warehouse notes, not product names:
"lost", "damaged", "damages", "wet", "short", "invcd as 84879?", "85123a mixed".
Conclusion: these are inventory write-offs / stock adjustments,
not customer returns.

## 5 Part 3 verified on ALL rows (not just the sample)
rows = 3,457 | price_zero = 3,457 | no_customer = 3,457
100% of these rows have zero price and no customer. Pattern confirmed.

Side finding: the description column is sometimes used for free-text
staff notes, so it can't be trusted as a product name everywhere.

## 5 part4 - C-invoice with positive quantity:
1 row: C496350, stock_code "M" (Manual), qty 1, price 373.57, no customer.
This is a manual accounting adjustment, not a product return.
Excluded anyway: no customer_id, and "M" is a non-product code.(see Q7).

## Q6 Price anomalies

### Part 1 - price classes
- positive: 1,061,164 rows (min 0.001, max 38,970)
- zero:         6,202 rows
- negative:         5 rows (min -53,594.36)
Check: sums to 1,067,371.
Max price 38,970 is too high for a gift shop item - check in Q7.

### Part 2 - negative prices (5 rows)
All stock_code "B", description "Adjust bad debt", no customer.
These are accounting write-offs of unpaid debt, not sales.
Total = -158,676. Would wrongly reduce revenue if included.
New finding: invoice numbers start with "A" - a third invoice type
(normal / C = cancellation / A = adjustment).

Not a duplicate - a correction sequence on 2011-08-12:
  14:50 A563185  +11,062.06  (entered with wrong sign)
  14:51 A563186  -11,062.06  (reverses it)
  14:52 A563187  -11,062.06  (correct entry)
Net = -11,062.06 = one real bad-debt write-off.
Net effect of all 6 B rows = -147,614 (not -158,676 from the 5 negatives alone).
Lesson: never deduplicate by matching amounts - deleting A563187 as a
"duplicate" would have wiped out the real write-off.
Irrelevant to analysis: all B rows are excluded as non-product codes.

### Part 3 - zero-price rows (6,202)
- 3,457 no customer, negative qty  -> the Q5 write-offs (same rows)
- 2,674 no customer, positive qty  -> internal stock adjustments
-    71 has customer, positive qty -> free items / samples to real customers
Check: 3,457 + 2,674 + 71 = 6,202.

### Cleaning decision
- Keep only unit_price > 0 for revenue and customer analysis.
- Bad-debt rows (B / A-invoices): exclude - accounting entries, not sales.
- The 71 free items to customers: exclude - not a purchase, and they
  would inflate a customer's purchase frequency in RFM without revenue.
- Log each group separately in the exclusion ledger.


## Q7 Non-product stock codes

### Part 1 - categories (top 25 non-5-digit codes)
- Postage/shipping: POST (+112,341), DOT (+322,647), C2 carriage (+13,386)
- Fees/charges: AMAZONFEE (-260,764), BANK CHARGES (-35,563), CRUK commission (-7,933)
- Accounting adjustments: M/m manual (-82,796), ADJUST (+6,835), B bad debt (-147,614)
- Discounts/samples: D (-13,485), S (-6,066)
- Gift vouchers: gift_0001_10/20/30/40/50
- Test data: TEST001
- REAL products: DCGS* codes (see Part 3)
Note: "M" and "m" are the same code in different case -> rule must be case-insensitive.

### Part 2 - highest prices
The 38,970 max price is stock code M (Manual) on a cancellation,
WITH a customer_id (15098). Also M 25,111 on customer 17399.
-> The no-customer rule does NOT catch these. Without a stock-code rule,
   these customers get huge negative monetary values in RFM.
Reversal pairs exist: C512770 / 512771 (25,111.09), C537630 / 537632
(13,541.33) - an entry and its correction.

### Part 3 - DCGS codes
DCGS* = dotcom gift shop products (gum, party bags, collars, ashtray).
They fail the 5-digit rule but ARE real products.
-> A regex "must start with 5 digits" rule would wrongly drop real sales.

### Cleaning decision (updated after checking ALL 28 non-5-digit codes)
Remove these non-product codes (case-insensitive, so "m" = "M"):
- Postage/carriage: POST, DOT, C2, C3
- Adjustments: M, ADJUST, ADJUST2, B
- Fees: AMAZONFEE, BANK CHARGES, CRUK
- Discounts/samples: D, S
- Test data: TEST001, TEST002
- Gift vouchers: GIFT, gift_0001_* (10 to 90)

Keep as real products despite failing the 5-digit rule:
- DCGS* (dotcom gift shop items), SP* (e.g. SP1002 chalkboard), PADS

Assumptions:
- C3 and GIFT have NULL descriptions; classified by naming pattern
  (C2 = carriage, gift_* = voucher). Both are 1 row, value 0 - no impact.
- Gift vouchers excluded: revenue is realised when the voucher is spent on
  real products, which are already recorded. Counting both double-counts.

Lesson: the top-25 list missed 9 codes (C3, ADJUST2, TEST002, GIFT,
gift_0001_60/70/80/90, SP1002). Always check the full list before writing
an exclusion rule.
Note: any_value() returns an arbitrary row - fine for exploring, never
for reproducible output.



## Extra: Rows per country
- United Kingdom: 981,330 rows, 5,410 customers (~181 rows per customer)
- EIRE: 17,866 rows, only 5 customers (~3,573 rows per customer)
- Other countries: 90-223 rows per customer
EIRE is ~20x every other country -> almost certainly wholesalers,
not individual shoppers.
Impact: a handful of wholesale accounts will dominate RFM "Champions"
and revenue concentration. Flag this when presenting top-customer results.
Caveat: rows include null-customer rows, so UK's 181 is inflated
(most anonymous sales are UK). Compare EIRE with Germany/France instead.


## Q8 Duplicate rows

### Part 1 - sheets overlap
- Year 2009-2010: 2009-12-01 -> 2010-12-09 (525,461 rows)
- Year 2010-2011: 2010-12-01 -> 2011-12-09 (541,910 rows)
1-9 Dec 2010 is in BOTH sheets -> stacking them double-counts those 9 days.

### Part 2
1,088 invoices appear in both sheets.

### Part 3/4 - duplicate rows
Key = invoice_no + stock_code + invoice_date + quantity + unit_price
(source_sheet deliberately ignored)
- Total duplicate rows:              34,337
- Within the same sheet:             12,135
- Caused by the sheet overlap:       22,202  (34,337 - 12,135)

### Cleaning decision
Deduplicate on the business key, ignoring source_sheet.
Assumption: identical lines (same invoice, product, qty, price, minute)
inside one sheet are export duplicates, not real repeat lines - a till
would merge them. Impact: 12,135 rows (~1.1%).

### Answer-key issues found
- README says 34,337 duplicates; exclusion_ledger.csv says 34,335.
  My result (34,337) matches the README; the CSV is stale.
- profile_raw.md "exact duplicate rows 32,907" counts duplicated GROUPS,
  not duplicate ROWS (computes "extra" but never sums it). Mislabelled.


  ## Step 7 - Exclusion ledger
Raw 1,067,371 -> duplicates -34,337 -> service codes -5,801
-> write-offs -3,391 -> non-positive price -2,572 -> clean 1,021,270 (95.68%)

Why ledger numbers are smaller than profiling numbers:
the ledger is a waterfall - each row is counted under the FIRST rule
that removes it, so nothing is counted twice.
- Write-offs 3,457 -> 3,391: 64 were duplicates, 2 were service codes.
  Check: 64 + 2 + 3,391 = 3,457.
- Non-positive prices 6,207 -> 2,572: 188 duplicates, 56 service codes,
  3,391 write-offs (all write-offs have price 0).
  Check: 188 + 56 + 3,391 + 2,572 = 6,207.

  ## Step 8 - Cohort retention
Definitions: cohort = first net-positive month; retained = net-positive
spend that month; denominator = period-0 size, fixed. No-ID customers excluded.
Traps handled:
1. Missing zeros -> complete cohort x period grid + LEFT JOIN
2. Unobservable periods -> grid capped at each cohort's last observable month
3. Partial last month -> Dec 2011 (9 days) excluded; last complete month = Nov 2011.
   The answer key misses this: its Dec-2009 cohort drops to 19.53% in month 24
   (Dec 2011) from ~30-40% - a data artifact, not churn.
4. Float residue -> money stored as DECIMAL (Step 7)
Output: 300 rows (24 cohorts, Dec 2009 - Nov 2011), all 4 checks OK.

### Step 8 findings
Checkpoints match answer key: Dec-2009 942/330/35.03%, Jan-2010 369/77/20.87%.

Left-censoring: Dec 2009 cohort avg retention (months 1-12) = 38.06% vs
18.16% for all later cohorts. Dec 2009 is the first month of data, so it
labels long-standing customers as "new". Excluded from all benchmarks.

Partial-month fix impact: later-cohort benchmark = 18.16% (mine) vs 17.6%
(answer key). The only difference is excluding the 9-day Dec 2011, so the
partial month was dragging the benchmark down by ~0.56 points.

Honest retention curve (excluding Dec 2009):
- Month 1: 20.67% -> ~79% of new customers do not return next month
- Decays to 13.42% by month 10 (the pooled curve incl. Dec 2009 looked flat
  at 20-25% - that flatness was the Dec 2009 contamination)
- Month 12 spike to 18.44%: Christmas seasonality (gift shop)

Headline: the business loses ~4 in 5 new customers after their first month,
and even the ones who return keep drifting away over the year.

### Step - 9 RFM Segmentation

RFM results (5,832 customers, all 7 checks OK):
- Champions: 21.3% of customers -> 68.6% of revenue
- At Risk - High Value: 210 customers, GBP 851K, avg 9.6 orders,
  338 days since last purchase -> the win-back target
- Hibernating + Lost: 41% of customers, 7.4% of revenue
- New / Promising: 503 customers, 1.5 orders avg -> where the month-1
  retention cliff happens; getting a 2nd order is the biggest lever
Fix impact vs answer key: At Risk - High Value avg orders 11.6 -> 9.6
(cancellations were counted as orders); customer 18102 147 -> 145 orders.
Caveats: segment thresholds are business conventions, not data-driven;
Champions include the EIRE wholesale accounts.