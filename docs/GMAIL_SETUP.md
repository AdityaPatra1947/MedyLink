# Gmail email verification

The application sends six-digit verification codes, password reset links, and provider review decisions using Django's configured email backend. Mobile numbers are contact details only; there is no SMS verification.

For Gmail, enable Google account 2-Step Verification and create an app password, if your account supports it. Use that app password for SMTP. See [Google's app password instructions](https://support.google.com/accounts/answer/185833?hl=en).

From PowerShell, run the helper. It asks for your email address and hides the app-password input. It checks the Gmail TLS connection and authentication before updating SMTP settings; database and other settings remain intact.

```powershell
# Run from the cloned MedyLink repository root.
.\.venv\Scripts\python.exe scripts\configure-smtp.py
```

To check saved settings later without sending an email:

```powershell
.\.venv\Scripts\python.exe scripts\configure-smtp.py --check
```

SMTP authentication does not prove inbox delivery. Register with an inbox you control after restarting the backend to exercise actual verification delivery.

Alternatively, edit the existing values in `backend/.env` locally:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your-address@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL="MedyLink <your-address@gmail.com>"
```

Google documents `smtp.gmail.com` and port 587 for STARTTLS in its [SMTP settings](https://support.google.com/mail/answer/7104828?hl=en). Work/school accounts may need their administrator to enable this configuration.

Keep the existing database and application secrets. Do not commit `.env` or paste the app password into chat. Restart the application after updating it:

```powershell
# Stop the existing development server with Ctrl+C first.
npm run dev
```

Register with an inbox you control, check its inbox/spam folder, and enter the six-digit code in the application. Codes expire after 10 minutes and can be used once. Before verification, sign-in is denied. After verification, patients can sign in; doctors and pharmacists wait for administrator review before accessing patient information. All roles use email and password to sign in. The resend control requests a new code after a 60-second cooldown without revealing whether an account exists. Resending invalidates the previous code. Five wrong attempts end the challenge; request a new code to try again.

Email verification does not require opening a link. `FRONTEND_ORIGIN` controls password-reset and provider-notification links. `http://localhost:3000` opens on the computer reading the email; use the deployed HTTPS origin for people accessing a hosted application.

Until the SMTP values are configured, keep `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` for local development. Verification messages then appear in the backend terminal and are not delivered to an inbox.
