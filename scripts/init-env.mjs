import { existsSync, writeFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
if (!existsSync('backend/.env')) {
  writeFileSync('backend/.env', `# Add your Neon connection string locally. Never commit this file.
DATABASE_URL=
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=${randomBytes(48).toString('hex')}
JWT_SIGNING_KEY=${randomBytes(48).toString('hex')}
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend
FRONTEND_ORIGIN=http://localhost:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000
REDIS_URL=
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=MedyLink <noreply@example.com>
`);
  console.log('Created backend/.env with random development secrets. Add DATABASE_URL next.');
} else console.log('Kept your existing backend/.env.');
