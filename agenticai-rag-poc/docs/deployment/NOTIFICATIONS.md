# Notifications Setup Guide

The application supports two zero-cost notification channels for alert delivery:

| Channel | Mechanism | Requires |
|---------|-----------|---------|
| **Email** | SMTP with STARTTLS | SMTP server + credentials set via environment variables |
| **ntfy.sh** | HTTP push | Only an ntfy topic (no account, no env vars beyond the topic itself) |

> **Why does "Send test notification" fail when I enter my Gmail address?**
>
> The **Email** field in Settings UI sets the *recipient* address only. The *sender* SMTP credentials must be configured in backend environment variables before the backend can actually send any email. Without `NOTIFICATION_SMTP_HOST` set, the backend skips SMTP entirely and returns an error. See [Gmail setup](#gmail-smtp) below.

---

## Quick start — ntfy.sh (zero config, no SMTP needed)

[ntfy.sh](https://ntfy.sh) is a free, open, anonymous push notification service. No account or SMTP credentials required.

1. Choose a long, random, secret topic name — treat it like a password (anyone who knows it can subscribe):

   ```
   my-rag-app-alerts-c7f2a9b4e1
   ```

2. Subscribe to that topic on any device. Options:
   - **Browser**: open `https://ntfy.sh/<your-topic>` and allow notifications
   - **Android / iOS**: install the ntfy app and subscribe to the topic
   - **CLI**: `curl -s https://ntfy.sh/<your-topic>/json`

3. In the app Settings UI → **Notifications**:
   - Enable the toggle
   - Enter the topic in **ntfy topic** field
   - Save settings
   - Click **Send test notification** — a push notification should arrive within seconds

4. Optionally pin the topic in `backend/.env` so it survives restarts:

   ```env
   NOTIFICATION_ENABLED=true
   NOTIFICATION_NTFY_TOPIC=my-rag-app-alerts-c7f2a9b4e1
   ```

---

## Email via SMTP

Email delivery requires an SMTP relay. The backend connects with STARTTLS on port 587. You need:

- An SMTP host (Gmail, Outlook, your own mail server, SendGrid, Mailgun, etc.)
- SMTP credentials (username + password/app password)
- All values set as **environment variables** before starting the server

### Environment variables

Add these to `backend/.env` and restart the backend:

```env
NOTIFICATION_ENABLED=true
NOTIFICATION_EMAIL=recipient@example.com         # who receives the alert
NOTIFICATION_SMTP_HOST=smtp.example.com          # your SMTP relay
NOTIFICATION_SMTP_PORT=587                       # 587 for STARTTLS (recommended)
NOTIFICATION_SMTP_USER=sender@example.com        # the "From" address / SMTP login
NOTIFICATION_SMTP_PASSWORD=your-smtp-password    # never logs this value (OWASP A09)
```

> The UI **Email** field sets `NOTIFICATION_EMAIL` at runtime and survives restarts via the encrypted settings cookie. All other SMTP fields (`NOTIFICATION_SMTP_HOST`, `NOTIFICATION_SMTP_PORT`, `NOTIFICATION_SMTP_USER`, `NOTIFICATION_SMTP_PASSWORD`) are environment-variable only — they cannot be set through the UI.

---

## Gmail SMTP

Gmail is the most common provider. Google blocks plain password SMTP — you **must** use an App Password.

### Prerequisites

1. Your Gmail account must have **2-Step Verification enabled**  
   → [myaccount.google.com/security](https://myaccount.google.com/security) → 2-Step Verification → Turn On

2. Generate a **Gmail App Password** (not your Gmail login password):  
   → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)  
   → App: *Mail* | Device: *Other (custom name)* → type `RAG App` → **Generate**  
   → Copy the 16-character password shown (e.g., `abcd efgh ijkl mnop` — spaces are ignored)

### `.env` configuration

```env
NOTIFICATION_ENABLED=true
NOTIFICATION_EMAIL=you@gmail.com                # recipient (can be your own Gmail)
NOTIFICATION_SMTP_HOST=smtp.gmail.com
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USER=you@gmail.com            # sender — same Gmail account
NOTIFICATION_SMTP_PASSWORD=abcdefghijklmnop     # 16-char App Password (no spaces)
```

### Step-by-step

1. Enable 2-Step Verification on your Google account (link above).

2. Generate an App Password:
   - Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - If the page doesn't exist, 2-Step Verification is not enabled — repeat step 1.
   - Name the app password `RAG App` (any label), click **Generate**.
   - Copy the 16-character password. This is shown only once.

3. Add to `backend/.env`:

   ```env
   NOTIFICATION_ENABLED=true
   NOTIFICATION_EMAIL=you@gmail.com
   NOTIFICATION_SMTP_HOST=smtp.gmail.com
   NOTIFICATION_SMTP_PORT=587
   NOTIFICATION_SMTP_USER=you@gmail.com
   NOTIFICATION_SMTP_PASSWORD=abcdefghijklmnop
   ```

4. Restart the backend:

   ```bash
   # Local / Docker Compose
   cd backend && source .venv/bin/activate
   uvicorn app.main:app --reload --port 8000
   ```

5. In the Settings UI → **Notifications**:
   - Enable the toggle
   - Enter your Gmail address in the **Email** field
   - Save settings
   - Click **Send test notification** → check your Gmail inbox

> **Troubleshooting Gmail**
> - *"Username and Password not accepted"* — the App Password is wrong or 2FA is not active.
> - *"Less secure app access"* — you are using your regular password, not an App Password.
> - *Connection timeout* — your server/firewall blocks outbound port 587. Try port 465 with SSL (requires code change — use ntfy.sh instead).
> - *Email lands in Spam* — add yourself to Gmail contacts; click "Not spam" once.

---

## Outlook / Microsoft 365

```env
NOTIFICATION_SMTP_HOST=smtp.office365.com
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USER=you@outlook.com
NOTIFICATION_SMTP_PASSWORD=your-outlook-password
```

> Microsoft accounts with Modern Authentication (OAuth) may block plain SMTP. Enable SMTP AUTH per mailbox:  
> Microsoft 365 admin → Users → Active users → your account → Mail tab → Manage email apps → enable **Authenticated SMTP**.

---

## SendGrid (for production / Vercel)

SendGrid's SMTP relay works on Vercel serverless (no port 587 blocking):

```env
NOTIFICATION_SMTP_HOST=smtp.sendgrid.net
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USER=apikey
NOTIFICATION_SMTP_PASSWORD=SG.your-sendgrid-api-key
```

Generate a SendGrid API key at [app.sendgrid.com/settings/api_keys](https://app.sendgrid.com/settings/api_keys) with **Mail Send** permission.

---

## Vercel deployment

Environment variables must be added in the Vercel dashboard — `.env` files are not deployed.

1. Open your Vercel project → **Settings** → **Environment Variables**
2. Add each variable (`NOTIFICATION_SMTP_HOST`, etc.) for **Production** (and optionally Preview)
3. Redeploy — Vercel propagates new env vars on the next build

Because Vercel serverless functions are stateless, the SMTP credentials are read from env on every cold start — no extra steps needed.

---

## Both channels simultaneously

You can enable email and ntfy.sh together. The backend attempts both independently and reports the status of each:

```env
NOTIFICATION_ENABLED=true
# Email
NOTIFICATION_EMAIL=you@gmail.com
NOTIFICATION_SMTP_HOST=smtp.gmail.com
NOTIFICATION_SMTP_PORT=587
NOTIFICATION_SMTP_USER=you@gmail.com
NOTIFICATION_SMTP_PASSWORD=abcdefghijklmnop
# ntfy.sh
NOTIFICATION_NTFY_TOPIC=my-rag-app-alerts-c7f2a9b4e1
```

The test result panel shows `email_sent: true / false` and `ntfy_sent: true / false` separately so you can verify both channels independently.

---

## When notifications fire

Notifications are sent automatically by the backend in one situation:

| Event | Condition | Dedup window |
|-------|-----------|--------------|
| Admin document near-limit warning | `admin_doc_count ≥ 80% of admin_doc_limit` | 24 hours — fires at most once per day |

Use **Send test notification** in the Settings UI to verify the channel is working without waiting for the real event to fire.

---

## Security notes (OWASP A09)

- `NOTIFICATION_SMTP_PASSWORD` is never written to logs (structlog omits it).
- The ntfy topic is treated as a shared secret — masked in Settings UI responses (`abcd***`).
- Both channels are disabled by default (`NOTIFICATION_ENABLED=false`).
- Admin role is required to change notification settings or trigger test delivery.
