/**
 * Demo document generator — shared by the admin walkthrough AND deployment
 * operations (data seeding, smoke tests, demo environments).
 *
 * Generates 4 demo documents (one per supported file type: .txt, .csv, .xlsx,
 * .pdf) on 4 randomly chosen topics from a pool of 8 enterprise content themes.
 *
 * Non-repetition guarantee:
 *   A topic-combination hash is stored in the OS temp directory.  The last 5
 *   combinations are remembered; the same combination cannot be chosen twice
 *   within 5 consecutive runs.
 *
 * Two usage modes — use the right function for the right context:
 *
 *   getWalkthroughDocSet()   — Walkthrough / demo recording.
 *     Always picks topics randomly. The WALKTHROUGH_TOPICS env var is
 *     intentionally IGNORED so every demo run exercises fresh content and
 *     prevents cached query suggestions from appearing.
 *
 *   getDeploymentDocSet()    — Deployment seeding / smoke tests.
 *     Checks the WALKTHROUGH_TOPICS env var first; falls back to random.
 *     Set WALKTHROUGH_TOPICS to a comma-separated list of topic IDs to pin
 *     topics for a reproducible demo environment.
 *     e.g. WALKTHROUGH_TOPICS="hr-policy,it-security,training-catalog,finance-budget"
 *
 * Topic IDs (for WALKTHROUGH_TOPICS / getDeploymentDocSet):
 *   hr-policy | it-security | travel-expense | training-catalog |
 *   project-portfolio | vendor-procurement | customer-faq | finance-budget
 */

import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import * as XLSX from 'xlsx'
import { PDFDocument, StandardFonts, rgb } from 'pdf-lib'

// ── Shared types ───────────────────────────────────────────────────────────────

export interface DemoDoc {
  /** File name with extension — used by the upload component and backend. */
  name: string
  /** MIME type for Playwright's setInputFiles. */
  mimeType: string
  /** File content: string for txt/csv, Buffer for xlsx/pdf. */
  content: string | Buffer
  /** Short human-readable topic label for walkthrough captions. */
  topic: string
}

export interface AdminDocSet {
  /** Four documents in order: .txt, .csv, .xlsx, .pdf */
  docs: [DemoDoc, DemoDoc, DemoDoc, DemoDoc]
  /** Combined label listing all four topics. */
  label: string
}

// ── Topic definitions ──────────────────────────────────────────────────────────

export interface TopicContent {
  id: string
  label: string
  /** Returns plain-text content for the .txt file. */
  txt: () => string
  /** Returns headers + rows for the .csv file. */
  csv: () => { headers: string[]; rows: string[][] }
  /** Returns sheet config for the .xlsx file. */
  xlsx: () => { sheetName: string; headers: string[]; rows: string[][] }
}

export const TOPICS: readonly TopicContent[] = [
  // ── A: HR & Employee Policy ─────────────────────────────────────────────────
  {
    id: 'hr-policy',
    label: 'HR & Employee Policy',
    txt: () => `ACME CORPORATION — EMPLOYEE HANDBOOK & HR POLICY
Version 4.2 | Effective: January 2025

1.1 Annual Leave Entitlement
Full-time employees receive 20 days of paid annual leave per year.
Employees with 5 or more years of continuous service receive 25 days.
Up to 10 unused days may be carried forward to the following year.

1.2 Sick Leave Policy
Employees receive 12 paid sick days per year. A medical certificate is required
for absences exceeding 3 consecutive days. Long-term illness over 30 days triggers
an occupational health referral and access to the Employee Assistance Programme.

1.3 Parental Leave
Maternity leave is 26 weeks at full pay, plus 26 optional unpaid weeks.
Paternity leave is 4 paid weeks taken within 56 days of birth.
Shared Parental Leave allows partners to share up to 50 weeks of leave.

1.4 Remote Work Policy
Employees work on-site at least 3 days per week (Tuesday–Thursday are core
collaboration days). Remote eligibility requires role suitability, good performance
standing, and completion of the 90-day probationary period. A £400 one-time
home-office allowance is provided; corporate VPN use is mandatory.

1.5 Compensation and Benefits
Annual salary reviews occur in March with a 4% merit budget. Benefits include
Bupa private medical insurance, a 6% company pension contribution matched by a
minimum 4% employee contribution, life assurance at 4× salary, cycle-to-work
scheme (up to £2,000), and a £1,500 professional development fund per year.

1.6 Performance Management
Performance is reviewed in July (mid-year) and December (year-end). Ratings:
Exceptional (10%), Exceeds Expectations (20%), Meets Expectations (60%),
Developing (7%), Needs Improvement (3%). Two consecutive Needs Improvement
ratings trigger a 90-day Performance Improvement Plan.`,
    csv: () => ({
      headers: ['policy_id', 'policy_name', 'category', 'entitlement', 'notes'],
      rows: [
        ['POL-001', 'Annual Leave', 'Leave', '20 days per year (25 after 5 years)', 'Max 10 days carry-forward'],
        ['POL-002', 'Sick Leave', 'Leave', '12 days per year', 'Medical cert required after 3 days'],
        ['POL-003', 'Maternity Leave', 'Parental', '26 weeks paid + 26 weeks unpaid', 'Notify HR 15 weeks before due date'],
        ['POL-004', 'Paternity Leave', 'Parental', '4 weeks paid', 'Within 56 days of birth'],
        ['POL-005', 'Compassionate Leave', 'Leave', '3-5 days paid', '5 days for immediate family'],
        ['POL-006', 'Remote Work Allowance', 'Benefits', '£400 one-time home-office allowance', 'Corporate VPN mandatory'],
        ['POL-007', 'Professional Development', 'Benefits', '£1500 per year', 'Pre-approved courses only'],
        ['POL-008', 'Pension', 'Benefits', '6% employer + 4% employee minimum', 'Salary sacrifice up to 20%'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'HR Policies',
      headers: ['Policy ID', 'Name', 'Category', 'Entitlement', 'Eligibility', 'Approval Required'],
      rows: [
        ['POL-001', 'Annual Leave', 'Leave', '20 days (25 after 5 yrs)', 'All full-time', 'Manager'],
        ['POL-002', 'Sick Leave', 'Leave', '12 days per year', 'All employees', 'Automatic'],
        ['POL-003', 'Maternity Leave', 'Parental', '26 wks paid + 26 wks unpaid', '1 yr service', 'HR Director'],
        ['POL-004', 'Paternity Leave', 'Parental', '4 weeks paid', '1 yr service', 'Manager + HR'],
        ['POL-005', 'Remote Work', 'Working Arrangements', '2 days per week', 'Role-dependent', 'Manager'],
        ['POL-006', 'Home Office Allowance', 'Benefits', '£400 one-time', 'Remote-eligible staff', 'HR'],
        ['POL-007', 'Private Medical', 'Benefits', 'Bupa Plan B', 'All employees + dependants', 'Automatic'],
      ],
    }),
  },

  // ── B: IT Security ──────────────────────────────────────────────────────────
  {
    id: 'it-security',
    label: 'IT Security Policy',
    txt: () => `GLOBALTECH — IT SECURITY AND ACCEPTABLE USE POLICY
Document ID: IT-SEC-002 | Version 3.0 | January 2025

1.1 Password Requirements
Passwords must be at least 14 characters long, combining uppercase, lowercase,
numbers, and special characters. They expire every 90 days and cannot be reused
for the previous 12 cycles. User names and dictionary words are prohibited.

1.2 Multi-Factor Authentication
MFA is mandatory for all corporate accounts, VPN access, cloud consoles, and
admin portals. Approved methods: authenticator app (TOTP), hardware security key
(FIDO2/WebAuthn), or SMS OTP as a last resort.

1.3 Privileged Access Management
Administrator credentials are managed via CyberArk Privileged Access Workstation.
All privileged sessions are recorded and retained for 12 months. Just-in-time
access elevation is required for all production systems.

1.4 Device and Endpoint Policy
Only company-issued or MDM-enrolled BYOD devices may access corporate resources.
macOS uses FileVault 2; Windows uses BitLocker. Operating systems must be patched
within 30 days of a critical update; zero-day patches within 72 hours.

1.5 Data Classification
Data tiers: Public, Internal, Confidential, and Restricted. DLP rules block
transmission of Confidential or Restricted data outside approved channels.
Violations require an incident report within 24 hours.

1.6 Acceptable Use
Company systems must not be used for personal commercial activities, illegal
content, cryptocurrency mining, or circumventing security controls. Monitoring
software is deployed on all corporate devices per local privacy law.`,
    csv: () => ({
      headers: ['control_id', 'control_name', 'category', 'requirement', 'enforcement'],
      rows: [
        ['SEC-001', 'Password Policy', 'Identity', '14+ chars; 90-day expiry; no reuse x12', 'Automated AD policy'],
        ['SEC-002', 'MFA Enforcement', 'Identity', 'TOTP or FIDO2 for all accounts', 'Automated via Okta'],
        ['SEC-003', 'Privileged Access', 'Identity', 'JIT via CyberArk; sessions recorded 12 months', 'Quarterly audit'],
        ['SEC-004', 'Endpoint Encryption', 'Device', 'Full-disk encryption on all devices', 'MDM compliance check'],
        ['SEC-005', 'Patch Management', 'Vulnerability', 'Critical patches within 30 days', 'MDM automated'],
        ['SEC-006', 'Data Classification', 'Data', '4 tiers; DLP auto-block on Confidential and above', 'DLP + CASB'],
        ['SEC-007', 'Incident Response', 'Operations', '24h initial report; 72h root cause', 'SIEM alerting'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Security Controls',
      headers: ['Control ID', 'Name', 'Category', 'Requirement', 'Owner', 'Last Reviewed'],
      rows: [
        ['SEC-001', 'Password Policy', 'Identity and Access', '14+ chars; 90-day expiry', 'IT Security', '2025-01-10'],
        ['SEC-002', 'MFA Enforcement', 'Identity and Access', 'TOTP or FIDO2 mandatory', 'IT Security', '2025-01-10'],
        ['SEC-003', 'PAM', 'Privileged Access', 'JIT via CyberArk', 'CyberSec Team', '2024-11-15'],
        ['SEC-004', 'Full-Disk Encryption', 'Endpoint', 'BitLocker / FileVault 2', 'IT Ops', '2025-01-05'],
        ['SEC-005', 'Patch Management', 'Vulnerability Mgmt', '30-day SLA for critical', 'IT Ops', '2025-01-08'],
        ['SEC-006', 'Data Loss Prevention', 'Data Protection', 'DLP on email, endpoint, cloud', 'IT Security', '2024-12-20'],
      ],
    }),
  },

  // ── C: Travel & Expense ─────────────────────────────────────────────────────
  {
    id: 'travel-expense',
    label: 'Travel and Expense Policy',
    txt: () => `MERIDIAN GROUP — TRAVEL AND EXPENSES POLICY
Policy Reference: FIN-TRAV-01 | Version 2.0 | February 2025

1.1 Pre-Approval Requirements
Domestic travel exceeding 3 days or £500 requires manager approval. International
travel requires director-level approval at least 10 working days in advance via
the Travel Portal.

1.2 Class of Travel
Economy class is standard for flights under 6 hours. Business class is permitted
for flights of 6 hours or more, or for medical reasons with HR approval. Premium
economy is approved for 4–6 hour routes when economy is unavailable.

1.3 Hotel Accommodation Limits
Maximum nightly hotel rates (excl. VAT): London or New York or Tokyo £250;
European capitals £180; other UK and US cities £150; rest of world £120.

1.4 Meal Allowances
Daily meal allowances (all meals combined): UK £45, Western Europe £55,
North America £60, Asia Pacific £50, rest of world £40. Alcohol is not
reimbursable as a standalone item.

1.5 Ground Transportation
Taxis and ride-share are reimbursable for airport transfers or when public transit
is impractical. Personal vehicle use is reimbursed at 45p per mile for the first
10,000 miles (HMRC advisory rate).

1.6 Expense Submission
Expenses must be submitted within 30 days of expenditure. Receipts are required
for all items above £25. Hotel folios must itemise all charges. Approved expenses
submitted before Thursday midnight are reimbursed in the following Friday payroll.`,
    csv: () => ({
      headers: ['expense_type', 'category', 'limit', 'receipt_required', 'approval'],
      rows: [
        ['Domestic flight', 'Travel', 'Economy class', 'E-ticket', 'Manager'],
        ['International flight', 'Travel', 'Economy under 6h or Business 6h and above', 'E-ticket', 'Director'],
        ['Hotel London', 'Accommodation', '£250 per night excl VAT', 'Itemised folio', 'Manager'],
        ['Hotel Europe', 'Accommodation', '£180 per night excl VAT', 'Itemised folio', 'Manager'],
        ['Meals UK', 'Subsistence', '£45 per day all-inclusive', 'Over £25', 'No additional'],
        ['Meals USA', 'Subsistence', '£60 per day all-inclusive', 'Over £25', 'No additional'],
        ['Taxi or ride-share', 'Transport', 'Reasonable and necessary', 'Receipt', 'Manager'],
        ['Mileage', 'Transport', '45p per mile first 10000', 'Mileage log', 'Manager'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Expense Limits',
      headers: ['Expense Type', 'Max Limit', 'Currency', 'Receipt Threshold', 'Approval Level', 'Notes'],
      rows: [
        ['Economy Flight', 'Actual fare', 'GBP', 'E-ticket required', 'Manager', 'Under 6h mandatory economy'],
        ['Business Class Flight', 'Actual fare', 'GBP', 'E-ticket required', 'Director', 'Only for 6h and above'],
        ['Hotel London', '250 per night', 'GBP', 'Itemised folio', 'Manager', 'Excl VAT'],
        ['Hotel Europe', '180 per night', 'GBP', 'Itemised folio', 'Manager', 'Capital cities'],
        ['Meals UK', '45 per day', 'GBP', 'Over £25', 'None', 'All meals combined'],
        ['Mileage', '0.45 per mile', 'GBP', 'Mileage log', 'Manager', 'First 10000 miles'],
      ],
    }),
  },

  // ── D: Corporate Training ───────────────────────────────────────────────────
  {
    id: 'training-catalog',
    label: 'Corporate Training Catalog',
    txt: () => `NORTHSTAR TECHNOLOGIES — CORPORATE LEARNING AND DEVELOPMENT CATALOG
Issue 6 | Updated: Q1 2025

1.1 AI and Machine Learning Fundamentals
A 16-hour online self-paced course introducing ML concepts, supervised and
unsupervised learning, neural networks, and real-world applications. Includes
Python labs. Target audience: all employees. Awards the AI Practitioner Certificate.

1.2 Cybersecurity Awareness Training
A 2-hour mandatory annual course covering phishing recognition, password hygiene,
data classification, incident reporting, and social engineering defence. Required
for all employees. Completion renews the Annual Compliance Badge.

1.3 Leadership Essentials Programme
A 24-hour blended programme for managers and senior ICs covering situational
leadership, coaching conversations, feedback, and psychological safety. Awards the
Certified People Leader credential.

1.4 Data Analytics with Power BI
A 12-hour online course covering interactive dashboards, DAX formulas, data
modelling, and report publishing to the Power BI service. Target audience:
analysts, finance, and operations teams. Prepares for the Microsoft PL-300 exam.

1.5 Project Management Professional Preparation
A 40-hour instructor-led online programme covering PMBOK 7th edition, agile and
hybrid frameworks, stakeholder engagement, and risk management. Grants PMP exam
eligibility upon completion.

1.6 GDPR and Data Privacy
A 4-hour online compliance course covering GDPR principles, lawful bases for
processing, data subject rights, breach notification, and cross-border transfer
mechanisms. Required for legal, HR, marketing, and data engineering teams.`,
    csv: () => ({
      headers: ['course_id', 'course_name', 'category', 'duration_hours', 'delivery', 'target_audience', 'certification'],
      rows: [
        ['T001', 'AI and ML Fundamentals', 'Technology', '16', 'Online self-paced', 'All employees', 'AI Practitioner Certificate'],
        ['T002', 'Cybersecurity Awareness', 'Compliance', '2', 'Online self-paced', 'All employees', 'Annual Compliance Badge'],
        ['T003', 'Leadership Essentials', 'Leadership', '24', 'Blended instructor-led', 'Managers and senior ICs', 'Certified People Leader'],
        ['T004', 'Power BI Analytics', 'Analytics', '12', 'Online self-paced', 'Analysts finance operations', 'Microsoft PL-300 prep'],
        ['T005', 'PMP Exam Preparation', 'Project Management', '40', 'Online live', 'Project managers', 'PMP exam eligibility'],
        ['T006', 'GDPR and Data Privacy', 'Compliance', '4', 'Online self-paced', 'Legal HR marketing data', 'GDPR Compliance Certificate'],
        ['T007', 'Python for Data Engineering', 'Technology', '20', 'Online self-paced', 'Software and data engineers', 'Internal Data Engineer Badge'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Training Programs',
      headers: ['Course ID', 'Course Name', 'Category', 'Hours', 'Delivery', 'Target Audience', 'Certification', 'Cost per Seat'],
      rows: [
        ['T001', 'AI and ML Fundamentals', 'Technology', '16', 'Online self-paced', 'All employees', 'AI Practitioner Cert', 'Free internal'],
        ['T002', 'Cybersecurity Awareness', 'Compliance', '2', 'Online self-paced', 'All employees', 'Compliance Badge', 'Free mandatory'],
        ['T003', 'Leadership Essentials', 'Leadership', '24', 'Blended', 'Managers', 'CPL credential', '£800 per person'],
        ['T004', 'Power BI Analytics', 'Analytics', '12', 'Online self-paced', 'Analysts finance', 'PL-300 prep', '£150 per person'],
        ['T005', 'PMP Exam Prep', 'Project Management', '40', 'Online live', 'Project managers', 'PMP eligibility', '£1200 per person'],
        ['T006', 'GDPR and Data Privacy', 'Compliance', '4', 'Online self-paced', 'Legal HR marketing', 'GDPR Certificate', 'Free mandatory'],
      ],
    }),
  },

  // ── E: Project Portfolio ────────────────────────────────────────────────────
  {
    id: 'project-portfolio',
    label: 'Project Portfolio Status',
    txt: () => `VERTEX INNOVATIONS — PROJECT PORTFOLIO STATUS REPORT
PMO Quarterly Report | Q1 2025

1.1 Customer Portal Redesign (PRJ-001)
Status: In Progress — Amber. Budget: £450,000. Spent: £312,000 (69%). Completion: 72%.
Project Manager: Emma Lawson. Next milestone: User acceptance testing by 15 February.
Risk: Backend API integration delayed; mitigation via contractor resource.

1.2 ERP System Upgrade (PRJ-002)
Status: In Progress — Red. Budget: £1,200,000. Spent: £980,000 (82%). Completion: 68%.
Project Manager: David Kim. Issue: Data migration sign-off delayed — escalated to CIO.
Recovery plan submitted; revised go-live moved to August 2025.

1.3 AI-Powered Sales Forecasting (PRJ-003)
Status: Completed — Green. Final cost: £267,000 vs budget £280,000 (5% under).
Key outcome: 18% improvement in forecast accuracy. PIR complete.

1.4 Warehouse Automation Phase 2 (PRJ-004)
Status: Planning — Green. Budget: £620,000. Spent: £45,000 (7%). Completion: 8%.
Project Manager: Tom Bradley. Next milestone: Vendor selection by 28 February.

1.5 ISO 27001 Recertification (PRJ-005)
Status: In Progress — Green. Budget: £95,000. Spent: £71,000. Completion: 78%.
Next milestone: Stage 2 audit scheduled for 10 March.

1.6 Project Governance
A Project Charter formally authorises a project and grants the PM authority to use
resources. Projects above £50,000 require a Business Case with NPV, IRR, and a risk
register approved by the Investment Committee before work can begin.`,
    csv: () => ({
      headers: ['project_id', 'project_name', 'pm', 'status', 'rag', 'budget_gbp', 'spent_gbp', 'pct_complete', 'next_milestone'],
      rows: [
        ['PRJ-001', 'Customer Portal Redesign', 'Emma Lawson', 'In Progress', 'Amber', '450000', '312000', '72', 'UAT by 15 Feb'],
        ['PRJ-002', 'ERP System Upgrade', 'David Kim', 'In Progress', 'Red', '1200000', '980000', '68', 'Data migration sign-off'],
        ['PRJ-003', 'AI Sales Forecasting', 'Priya Nair', 'Completed', 'Green', '280000', '267000', '100', 'PIR completed'],
        ['PRJ-004', 'Warehouse Automation Ph2', 'Tom Bradley', 'Planning', 'Green', '620000', '45000', '8', 'Vendor selection 28 Feb'],
        ['PRJ-005', 'ISO 27001 Recertification', 'Aisha Mensah', 'In Progress', 'Green', '95000', '71000', '78', 'Stage 2 audit 10 Mar'],
        ['PRJ-006', 'Mobile App v3.0', 'Carlos Rivera', 'In Progress', 'Amber', '380000', '290000', '81', 'Beta defect resolution'],
        ['PRJ-007', 'Graduate Onboarding Redesign', 'Nina Park', 'Completed', 'Green', '55000', '52000', '100', 'PIR submitted'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Project Portfolio',
      headers: ['Project ID', 'Name', 'PM', 'Status', 'RAG', 'Budget (£)', 'Spent (£)', '% Complete', 'End Date', 'Next Milestone'],
      rows: [
        ['PRJ-001', 'Customer Portal Redesign', 'Emma Lawson', 'In Progress', 'Amber', '450000', '312000', '72%', '2025-03-31', 'UAT by 15 Feb'],
        ['PRJ-002', 'ERP System Upgrade', 'David Kim', 'In Progress', 'Red', '1200000', '980000', '68%', '2025-06-30', 'Data migration sign-off'],
        ['PRJ-003', 'AI Sales Forecasting', 'Priya Nair', 'Completed', 'Green', '280000', '267000', '100%', '2024-12-31', 'PIR completed'],
        ['PRJ-004', 'Warehouse Automation', 'Tom Bradley', 'Planning', 'Green', '620000', '45000', '8%', '2026-01-31', 'Vendor selection'],
        ['PRJ-005', 'ISO 27001 Recertification', 'Aisha Mensah', 'In Progress', 'Green', '95000', '71000', '78%', '2025-04-30', 'Stage 2 audit'],
        ['PRJ-006', 'Mobile App v3.0', 'Carlos Rivera', 'In Progress', 'Amber', '380000', '290000', '81%', '2025-02-28', 'Beta defects'],
      ],
    }),
  },

  // ── F: Vendor and Procurement ───────────────────────────────────────────────
  {
    id: 'vendor-procurement',
    label: 'Vendor and Procurement Policy',
    txt: () => `ACME CORPORATION — PROCUREMENT AND VENDOR MANAGEMENT POLICY
Policy Reference: PROC-01 | Version 1.4 | March 2025

1.1 Procurement Thresholds
Purchases below £5,000 are approved by a department manager. Purchases between
£5,000 and £50,000 require 3 competitive quotes and CFO approval. Purchases
above £50,000 require a formal RFP process and Board approval.

1.2 Vendor Onboarding
All new vendors must complete the Vendor Due Diligence Questionnaire covering
financial stability, data security, business continuity, and ESG commitments.
Vendors processing personal data must sign a Data Processing Agreement.

1.3 Contract Management
Standard vendor contracts use the company MSA template. Deviations require Legal
review. All contracts must include SLA definitions, termination for convenience
clauses, and liability caps.

1.4 SLA and Performance Monitoring
Critical vendors with annual spend above £200,000 are reviewed quarterly against
contracted SLAs. Two consecutive missed SLAs trigger a remediation plan. Three
consecutive failures may result in contract termination.

1.5 Preferred Vendor List
The Procurement team maintains a Preferred Vendor List with pre-negotiated rates
and pre-approved terms. Using list vendors accelerates approvals and reduces legal
review time. The list is reviewed and updated each January.`,
    csv: () => ({
      headers: ['vendor_id', 'vendor_name', 'category', 'annual_spend_gbp', 'sla_uptime_pct', 'contract_end', 'performance_rating', 'risk_level'],
      rows: [
        ['V001', 'CloudCore Infrastructure', 'Cloud Hosting', '1200000', '99.9', '2026-03-31', '4.5 of 5', 'Low'],
        ['V002', 'SecureNet Managed Services', 'Cybersecurity', '420000', '99.95', '2025-06-30', '4.7 of 5', 'Low'],
        ['V003', 'DataBridge Analytics', 'Data Engineering', '195000', '99.5', '2025-05-31', '4.2 of 5', 'Medium'],
        ['V004', 'LegalEdge LLP', 'Legal Services', 'Variable', 'N/A', 'Ongoing', '4.9 of 5', 'Low'],
        ['V005', 'TalentFirst Recruitment', 'Recruitment', '240000', 'N/A', '2024-12-31', '3.5 of 5', 'Medium'],
        ['V006', 'FaciliCare FM', 'Facilities Management', '310000', 'N/A', '2025-12-31', '4.0 of 5', 'Low'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Vendor Registry',
      headers: ['Vendor ID', 'Vendor Name', 'Category', 'Annual Spend (£)', 'SLA %', 'Contract End', 'Rating', 'Risk Level'],
      rows: [
        ['V001', 'CloudCore Infrastructure', 'Cloud Hosting', '1200000', '99.9%', '2026-03-31', '4.5 of 5', 'Low'],
        ['V002', 'SecureNet Managed Services', 'Cybersecurity', '420000', '99.95%', '2025-06-30', '4.7 of 5', 'Low'],
        ['V003', 'DataBridge Analytics', 'Data Engineering', '195000', '99.5%', '2025-05-31', '4.2 of 5', 'Medium'],
        ['V004', 'LegalEdge LLP', 'Legal Services', 'Variable', 'N/A', 'Ongoing', '4.9 of 5', 'Low'],
        ['V005', 'TalentFirst Recruitment', 'Recruitment', '240000', 'N/A', '2024-12-31', '3.5 of 5', 'Medium'],
      ],
    }),
  },

  // ── G: Customer FAQ ─────────────────────────────────────────────────────────
  {
    id: 'customer-faq',
    label: 'Customer Support Knowledge Base',
    txt: () => `NORTHSTAR TECHNOLOGIES — CUSTOMER SUPPORT KNOWLEDGE BASE
Version 2.1 | March 2025

1.1 How Do I Change My Subscription Plan?
Navigate to Account Settings then Billing then Change Plan. Upgrades apply
immediately with pro-rated credits. Downgrades take effect at the start of the
next billing cycle.

1.2 What Payment Methods Are Accepted?
Accepted: Visa, Mastercard, American Express, PayPal, and bank transfer for annual
plans. Enterprise customers on contracts of $10,000 or more can request invoiced
billing with Net-30 terms.

1.3 How Do I Request a Refund?
Refunds are available within 14 days of purchase for monthly plans and within
30 days for annual plans. Email billing@northstar.io. Processing takes 5–7 business days.

1.4 What Is the AI Assistant Feature?
The AI Assistant is a natural language interface for your data. It generates SQL,
interprets results, and presents insights in plain English. Available on
Professional and Enterprise plans. All inference runs within your security boundary.

1.5 What Is the Data Retention Policy?
Data is retained for the duration of your subscription plus 90 days post-cancellation.
During the 90-day window, export all data in CSV, JSON, or Parquet. Enterprise
customers may negotiate custom retention up to 7 years.

1.6 What Security Certifications Does NorthStar Hold?
NorthStar holds SOC 2 Type II, ISO 27001, and GDPR compliance certifications.
Healthcare customers benefit from HIPAA-eligible infrastructure. PCI DSS Level 1
compliance is available for customers processing payment card data.`,
    csv: () => ({
      headers: ['faq_id', 'question', 'category', 'answer_summary', 'plan_availability'],
      rows: [
        ['FAQ-001', 'How to change subscription plan', 'Billing', 'Account Settings then Billing then Change Plan', 'All plans'],
        ['FAQ-002', 'Accepted payment methods', 'Billing', 'Card PayPal bank transfer Net-30 for Enterprise', 'All plans'],
        ['FAQ-003', 'How to request a refund', 'Billing', '14 days monthly or 30 days annual window', 'All plans'],
        ['FAQ-004', 'What is the AI Assistant', 'Features', 'NL interface for data queries runs in your security boundary', 'Professional Enterprise'],
        ['FAQ-005', 'Data retention policy', 'Data', 'Active subscription plus 90 days post-cancellation', 'All plans'],
        ['FAQ-006', 'Where is data stored', 'Security', 'AWS in customer-chosen region US EU APAC AU', 'All plans'],
        ['FAQ-007', 'Security certifications', 'Security', 'SOC 2 Type II ISO 27001 GDPR HIPAA-eligible', 'Enterprise'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Support FAQ',
      headers: ['FAQ ID', 'Category', 'Question', 'Answer Summary', 'Plans', 'Last Updated'],
      rows: [
        ['FAQ-001', 'Billing', 'How to change subscription plan', 'Settings Billing Change Plan', 'All', '2025-01-15'],
        ['FAQ-002', 'Billing', 'Accepted payment methods', 'Card PayPal bank transfer', 'All', '2025-01-15'],
        ['FAQ-003', 'Features', 'What is AI Assistant', 'NL query interface for your data', 'Pro Enterprise', '2025-02-01'],
        ['FAQ-004', 'Security', 'Where is data stored', 'AWS regional data centres', 'All', '2025-01-20'],
        ['FAQ-005', 'Data', 'Data retention policy', 'Active sub plus 90 days post-cancel', 'All', '2025-01-20'],
      ],
    }),
  },

  // ── H: Finance and Budget ───────────────────────────────────────────────────
  {
    id: 'finance-budget',
    label: 'Departmental Budget and Financial Policy',
    txt: () => `MERIDIAN GROUP — ANNUAL BUDGET GUIDELINES AND FINANCIAL POLICY
Finance Reference: FIN-BUD-03 | FY 2025

1.1 Budget Planning Process
Departmental budgets are set annually in October for the following financial year.
Each department head submits a bottom-up budget request via the Finance Portal by
31 October. The CFO consolidates requests and presents the draft budget to the
Board by 30 November for approval.

1.2 Budget Categories
Operating expenditure covers day-to-day expenses: salaries, software licences,
travel, and marketing. Capital expenditure covers assets with a useful life
exceeding one year: hardware, office fit-out, and acquired IP. Projects below
£50,000 are expensed as OpEx; projects above £50,000 are typically capitalised
and depreciated over the asset's useful life.

1.3 Variance Reporting
Monthly variance reports compare actuals versus budget. Variances exceeding 10%
in any month require a written explanation within 5 working days. Cumulative
year-to-date variances above 15% trigger a formal reforecast.

1.4 Cost Centre Management
Each department has a designated cost centre code. All purchase orders, expenses,
and invoices must be coded correctly. Mis-coded transactions must be corrected
within 30 days of the period end.

1.5 Year-End Close
Accruals for uninvoiced goods and services received before 31 December must be
submitted to Finance by 20 December. Purchase orders not fully invoiced by year-end
are reviewed for carry-forward or cancellation.`,
    csv: () => ({
      headers: ['department', 'q1_budget_gbp', 'q1_actual_gbp', 'q2_budget_gbp', 'q2_actual_gbp', 'annual_budget_gbp', 'ytd_variance_pct'],
      rows: [
        ['Engineering', '850000', '820000', '870000', '890000', '3400000', '+1.2%'],
        ['Sales', '620000', '680000', '650000', '710000', '2600000', '+8.3%'],
        ['Marketing', '210000', '195000', '220000', '215000', '860000', '-3.5%'],
        ['Customer Success', '180000', '175000', '185000', '182000', '730000', '-1.8%'],
        ['Legal and Compliance', '95000', '92000', '95000', '98000', '380000', '+0.5%'],
        ['HR and People', '140000', '135000', '145000', '141000', '570000', '-2.0%'],
        ['Finance and Operations', '115000', '118000', '115000', '113000', '460000', '+0.7%'],
      ],
    }),
    xlsx: () => ({
      sheetName: 'Budget vs Actuals',
      headers: ['Department', 'Q1 Budget (£)', 'Q1 Actual (£)', 'Q2 Budget (£)', 'Q2 Actual (£)', 'Annual Budget (£)', 'YTD Variance %', 'Status'],
      rows: [
        ['Engineering', '850000', '820000', '870000', '890000', '3400000', '+1.2%', 'On Track'],
        ['Sales', '620000', '680000', '650000', '710000', '2600000', '+8.3%', 'Over Budget'],
        ['Marketing', '210000', '195000', '220000', '215000', '860000', '-3.5%', 'Under Budget'],
        ['Customer Success', '180000', '175000', '185000', '182000', '730000', '-1.8%', 'On Track'],
        ['Legal and Compliance', '95000', '92000', '95000', '98000', '380000', '+0.5%', 'On Track'],
        ['HR and People', '140000', '135000', '145000', '141000', '570000', '-2.0%', 'On Track'],
      ],
    }),
  },
]

export const TOPIC_IDS = TOPICS.map(t => t.id)

// ── File content builders ──────────────────────────────────────────────────────

function buildCsvString(headers: string[], rows: string[][]): string {
  const esc = (v: string) => v.includes(',') || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v
  return [headers.map(esc).join(','), ...rows.map(r => r.map(esc).join(','))].join('\n')
}

function buildXlsxBuffer(sheetName: string, headers: string[], rows: string[][]): Buffer {
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  XLSX.utils.book_append_sheet(wb, ws, sheetName)
  return XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' }) as Buffer
}

function wrapText(
  text: string,
  fontObj: { widthOfTextAtSize: (s: string, n: number) => number },
  fontSize: number,
  maxWidth: number,
): string[] {
  const result: string[] = []
  for (const paragraph of text.split('\n')) {
    const words = paragraph.split(' ')
    let line = ''
    for (const word of words) {
      const test = line ? `${line} ${word}` : word
      if (fontObj.widthOfTextAtSize(test, fontSize) > maxWidth) {
        if (line) result.push(line)
        line = word
      } else {
        line = test
      }
    }
    if (line) result.push(line)
    result.push('') // blank line between paragraphs
  }
  return result
}

async function buildPdfBuffer(topic: TopicContent): Promise<Buffer> {
  const pdfDoc = await PDFDocument.create()
  const regular = await pdfDoc.embedFont(StandardFonts.Helvetica)
  const bold = await pdfDoc.embedFont(StandardFonts.HelveticaBold)

  const A4 = { w: 595, h: 842 }
  const margin = 50
  const usableW = A4.w - margin * 2
  const black = rgb(0, 0, 0)

  let page = pdfDoc.addPage([A4.w, A4.h])
  let y = A4.h - margin

  const writeLine = (text: string, size: number, isBold = false) => {
    const f = isBold ? bold : regular
    if (y < margin + size + 4) {
      page = pdfDoc.addPage([A4.w, A4.h])
      y = A4.h - margin
    }
    page.drawText(text, { x: margin, y, size, font: f, color: black })
    y -= size + 4
  }

  // Title
  writeLine(topic.label.toUpperCase() + ' — REFERENCE DOCUMENT', 13, true)
  writeLine(`${topic.label} — Reference Document | Version 1.0 | ${new Date().getFullYear()}`, 9)
  y -= 6

  // Main content
  for (const line of wrapText(topic.txt(), regular, 10, usableW)) {
    writeLine(line, 10)
  }

  const bytes = await pdfDoc.save()
  return Buffer.from(bytes)
}

// ── Non-repetition history ─────────────────────────────────────────────────────

const HISTORY_FILE = path.join(os.tmpdir(), 'walkthrough-topic-history.json')
const MAX_HISTORY = 5

function readHistory(): string[] {
  try {
    const raw = fs.readFileSync(HISTORY_FILE, 'utf-8')
    const p = JSON.parse(raw)
    return Array.isArray(p) ? p : []
  } catch { return [] }
}

function writeHistory(h: string[]): void {
  try { fs.writeFileSync(HISTORY_FILE, JSON.stringify(h.slice(-MAX_HISTORY))) } catch { /* non-fatal */ }
}

function comboHash(indices: number[]): string {
  return crypto.createHash('md5').update(indices.sort().join(',')).digest('hex').slice(0, 8)
}

// ── Topic selection ────────────────────────────────────────────────────────────

/**
 * Always-random: picks 4 distinct topics, never repeating the same combination
 * in the last MAX_HISTORY runs. History is persisted in the OS temp directory
 * so it survives across test runs on the same machine.
 */
function pickRandomTopics(): [TopicContent, TopicContent, TopicContent, TopicContent] {
  const history = readHistory()
  for (let attempt = 0; attempt < 300; attempt++) {
    const shuffled = [...Array(TOPICS.length).keys()].sort(() => Math.random() - 0.5)
    const combo = shuffled.slice(0, 4)
    if (!history.includes(comboHash(combo))) {
      history.push(comboHash(combo))
      writeHistory(history)
      return combo.map(i => TOPICS[i]) as [TopicContent, TopicContent, TopicContent, TopicContent]
    }
  }
  // Fallback when the pool is exhausted (shouldn't happen with 8 topics / 4 slots)
  return [TOPICS[0], TOPICS[1], TOPICS[2], TOPICS[3]]
}

/**
 * Deployment-mode selector: checks WALKTHROUGH_TOPICS env var first,
 * then falls back to pickRandomTopics().
 */
function resolveDeploymentTopics(): [TopicContent, TopicContent, TopicContent, TopicContent] {
  const override = process.env.WALKTHROUGH_TOPICS
  if (override) {
    const ids = override.split(',').map(s => s.trim()).filter(Boolean)
    const resolved = ids
      .map(id => TOPICS.find(t => t.id === id))
      .filter((t): t is TopicContent => t !== undefined)
    if (resolved.length >= 4) {
      return [resolved[0], resolved[1], resolved[2], resolved[3]]
    }
    // Pad with random topics if fewer than 4 IDs were supplied
    const extras = TOPICS.filter(t => !resolved.includes(t))
    while (resolved.length < 4) resolved.push(extras[resolved.length % extras.length])
    return [resolved[0], resolved[1], resolved[2], resolved[3]]
  }
  return pickRandomTopics()
}

// ── Shared doc-set builder ─────────────────────────────────────────────────────

async function buildDocSet(
  [t0, t1, t2, t3]: [TopicContent, TopicContent, TopicContent, TopicContent],
): Promise<AdminDocSet> {
  const csvData  = t1.csv()
  const xlsxData = t2.xlsx()
  const pdfBuf   = await buildPdfBuffer(t3)

  const docs: [DemoDoc, DemoDoc, DemoDoc, DemoDoc] = [
    { name: `${t0.id}.txt`,  mimeType: 'text/plain',    content: t0.txt(), topic: t0.label },
    {
      name: `${t1.id}.csv`,
      mimeType: 'text/csv',
      content: buildCsvString(csvData.headers, csvData.rows),
      topic: t1.label,
    },
    {
      name: `${t2.id}.xlsx`,
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      content: buildXlsxBuffer(xlsxData.sheetName, xlsxData.headers, xlsxData.rows),
      topic: t2.label,
    },
    { name: `${t3.id}.pdf`,  mimeType: 'application/pdf',  content: pdfBuf, topic: t3.label },
  ]

  return { docs, label: [t0.label, t1.label, t2.label, t3.label].join(' · ') }
}

// ── Public API ─────────────────────────────────────────────────────────────────

/**
 * Guest walkthrough document — a single TXT file on a randomly chosen topic.
 *
 * The topic is picked at random from the full pool (no history tracking needed
 * for single-doc guest mode). The returned DemoDoc is passed directly to
 * setInputFiles as an in-memory buffer — no temp files, works for local and
 * remote (Vercel) deployments equally.
 *
 * Questions are then derived from this same content via generateWalkthroughQuestions,
 * so the indexed document always matches the queries asked.
 */
export async function getGuestDocSet(): Promise<DemoDoc> {
  const idx = Math.floor(Math.random() * TOPICS.length)
  const topic = TOPICS[idx]
  return {
    name: `${topic.id}.txt`,
    mimeType: 'text/plain',
    content: topic.txt(),
    topic: topic.label,
  }
}

/**
 * Admin walkthrough demo document set — always uses random topic selection.
 *
 * WALKTHROUGH_TOPICS env var is intentionally ignored so each walkthrough run
 * exercises fresh content and prevents cached query suggestions.
 *
 * File assignment:
 *   topic[0] → .txt   topic[1] → .csv   topic[2] → .xlsx   topic[3] → .pdf
 */
export async function getWalkthroughDocSet(): Promise<AdminDocSet> {
  return buildDocSet(pickRandomTopics())
}

/**
 * Deployment / seeding document set — respects the WALKTHROUGH_TOPICS env var
 * for operator-controlled topic selection, then falls back to random.
 *
 * Use in deployment seed scripts and smoke-test helpers so operators can pin
 * specific topics for reproducible demo environments.
 *
 * Set WALKTHROUGH_TOPICS to a comma-separated list of topic IDs:
 *   WALKTHROUGH_TOPICS="hr-policy,it-security,training-catalog,finance-budget"
 *
 * Available IDs: hr-policy | it-security | travel-expense | training-catalog |
 *   project-portfolio | vendor-procurement | customer-faq | finance-budget
 *
 * File assignment:
 *   topic[0] → .txt   topic[1] → .csv   topic[2] → .xlsx   topic[3] → .pdf
 */
export async function getDeploymentDocSet(): Promise<AdminDocSet> {
  return buildDocSet(resolveDeploymentTopics())
}
