/** Real registration + admin UI verification against isolated E2E servers only. */
import { readFile, readdir, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { chromium, expect } from '../frontend/node_modules/@playwright/test/index.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origin = 'http://127.0.0.1:3001';
const fixture = JSON.parse(await readFile(path.join(root, '.local/e2e-fixture.json'), 'utf8'));
const output = path.join(root, '.local/registration-workflow');
await mkdir(output, {recursive: true});
const run = randomBytes(5).toString('hex');
const password = randomBytes(18).toString('base64url') + '!';
const accounts = {};
const results = [];
const errors = [];
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAIAAADZF8uwAAAAF0lEQVR4nGP8//8/AyHARFDFqKIBCAIAP6kDFcAgiIsAAAAASUVORK5CYII=', 'base64');
async function verificationCode(email) {
  for (const name of await readdir(path.join(root, '.local/test-emails'))) {
    const content = (await readFile(path.join(root, '.local/test-emails', name), 'utf8')).replace(/=\r?\n/g, '');
    if (!content.includes(`To: ${email}`)) continue;
    const body = content.split(/\r?\n\r?\n/).slice(1).join('\n\n');
    const code = body.match(/\b[0-9]{6}\b/);
    if (code) {
      expect(body).not.toContain('/verify-email?token=');
      return code[0];
    }
  }
  throw new Error('Expected isolated verification code email was not written.');
}
const browser = await chromium.launch({channel: 'chrome', headless: true});
async function newPage(mobile = false) {
  const context = await browser.newContext({viewport: mobile ? {width:390,height:844} : {width:1440,height:1080}});
  const page = await context.newPage(); page.setDefaultTimeout(25000);
  page.on('pageerror', e => errors.push(e.message));
  return page;
}
async function json(page, pathname) {
  const response = await page.request.get(origin + '/api/v1' + pathname);
  expect(response.status()).toBe(200); return response.json();
}
async function login(page, email, pass) {
  await page.goto(origin + '/login');
  await page.locator('[name="email"]').fill(email);
  await page.locator('[name="password"]').fill(pass);
  await page.getByRole('button', {name:'Sign in',exact:true}).click();

}
try {
  const pendingPage = await newPage();
  await pendingPage.goto(origin + '/verify-email?token=retired-synthetic-token');
  await pendingPage.locator('[name="email"]').fill(fixture.pending_email);
  await pendingPage.getByRole('button',{name:'Send code',exact:true}).click();
  await expect(pendingPage.getByText('If this address needs verification, a code has been sent. Check your inbox and spam folder.',{exact:true})).toBeVisible();
  await expect(pendingPage.getByRole('button',{name:/Resend code in [0-9]+s/})).toBeDisabled();
  const requestedCode = await verificationCode(fixture.pending_email);
  await pendingPage.locator('[name="code"]').fill(requestedCode);
  await pendingPage.getByRole('button',{name:'Verify email',exact:true}).click();
  await expect(pendingPage.getByText('Your email is verified. You can now sign in.',{exact:true})).toBeVisible();
  await pendingPage.context().close();
  results.push('existing unverified account: old link opens code form, request sends code, cooldown displays, verification succeeds');
  for (const role of ['patient','doctor','pharmacist']) {
    const page = await newPage(role === 'pharmacist');
    const email = `registration-${role}-${run}@example.test`;
    const name = `Registration ${role} ${run}`;
    accounts[role] = {page,email,name};
    await page.goto(`${origin}/register/${role}`);
    for (const [key,value] of Object.entries({name,email,phone:'+919876543210',password,password_confirm:password})) {
      await page.locator(`[name="${key}"]`).fill(value);
    }
    await page.getByRole('button',{name:'Continue',exact:true}).click();
    const details = role === 'patient'
      ? {date_of_birth:'1990-05-12',address:'Synthetic patient address',emergency_contact:'Synthetic contact +919000000001'}
      : {registration_number:`REG-${role}-${run}`,registering_body:'SYNTHETIC TEST COUNCIL',practice_address:'Synthetic practice address',
          ...(role === 'doctor' ? {qualification:'Synthetic MBBS',specialty:'General medicine',clinic_name:'Synthetic clinic',years_experience:'5'}
            : {shop_name:`Synthetic pharmacy ${run}`,shop_license:`SHOP-${run}`,shop_license_expires:'2030-12-31',opening_hours:'Mon–Sat 09:00–18:00'})};
    for (const [key,value] of Object.entries(details)) await page.locator(`[name="${key}"]`).fill(value);
    if (role === 'patient') {
      await page.locator('[name="gender"]').selectOption('female');
      await page.locator('[name="blood_group"]').selectOption('O+');
    }
    await page.getByRole('button',{name:'Continue',exact:true}).click();
    if (role !== 'patient') {
      const evidenceFiles = role === 'pharmacist'
        ? [1,2,3].map(n=>({name:`synthetic-certificate-${n}.png`,mimeType:'image/png',buffer:Buffer.concat([png,Buffer.alloc(4*1024*1024-png.length)])}))
        : [{name:'synthetic-certificate.png',mimeType:'image/png',buffer:png}];
      await page.locator('[name="credential_documents"]').setInputFiles(evidenceFiles);
      await page.locator('[name="photo"]').setInputFiles({name:'synthetic-photo.png',mimeType:'image/png',buffer:png});
    }
    await page.locator('[name="consent"]').check();
    const responsePromise = page.waitForResponse(r => r.url().endsWith('/auth/register/') && r.request().method()==='POST');
    await page.getByRole('button',{name:role === 'patient' ? 'Create patient account' : role === 'doctor' ? 'Submit doctor application' : 'Submit pharmacy application',exact:true}).click();
    const response = await responsePromise;
    if (response.status() !== 202) throw new Error(`${role} signup failed: ${response.status()} ${await response.text()}`);
    await expect(page.getByRole('heading',{name:'Check your email',exact:true})).toBeVisible();
    const code = await verificationCode(email);
    if (role === 'patient') {
      await page.goto(origin + '/verify-email?token=retired-synthetic-token');
      await page.locator('[name="email"]').fill(email);
    }
    await page.screenshot({path:path.join(output,`${role}-verification.png`),fullPage:true});
    if (role === 'patient') {
      const incorrect = String((Number(code) + 1) % 1000000).padStart(6, '0');
      await page.locator('[name="code"]').fill(incorrect);
      await page.getByRole('button',{name:'Verify email',exact:true}).click();
      await expect(page.getByText('That code is invalid or has expired. Check the email address or request a new code.',{exact:true})).toBeVisible();
    }
    await page.locator('[name="code"]').fill(code);
    await page.getByRole('button',{name:'Verify email',exact:true}).click();
    await expect(page.getByText('Your email is verified. You can now sign in.',{exact:true})).toBeVisible();
    await login(page,email,password);
    await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
    if (role === 'patient') {
      const profile = await json(page,'/patients/me/');
      expect(profile.date_of_birth).toBe('1990-05-12');
      expect(profile.gender).toBe('female');
      expect(profile.blood_group).toBe('O+');
    } else {
      const {current} = await json(page,'/provider/application/');
      expect(current.status).toBe('pending'); expect(current.documents).toHaveLength(role === 'pharmacist' ? 4 : 2);
      expect(current.documents.filter(doc => doc.kind === 'credential')).toHaveLength(role === 'pharmacist' ? 3 : 1);
      expect(current.email_verified).toBe(true);
      accounts[role].application = current;
      const blocked = await page.request.get(origin + '/api/v1' + (role === 'doctor' ? '/doctor/patients/' : '/pharmacy/shared-prescriptions/'));
      expect(blocked.status()).toBe(403);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    results.push(`${role}: registration fields + file persistence, emailed verification code, login${role !== 'patient' ? ', pending access restriction' : ''}`);
  }
  const admin = await newPage();
  await login(admin,fixture.accounts.admin.email,fixture.password);
  await expect(admin.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  for (const [role,route] of [['doctor','/admin/doctors'],['pharmacist','/admin/pharmacists']]) {
    await admin.goto(origin + route);
    await expect(admin.getByRole('heading',{name:accounts[role].name,exact:true})).toBeVisible();
    const data = await json(admin,`/admin/provider-applications/?role=${role}&search=${run}`);
    expect(data.results).toHaveLength(1); expect(data.results[0].role).toBe(role);
    await admin.screenshot({path:path.join(output,`${role}-queue.png`),fullPage:true});
  }
  await admin.goto(origin + '/admin/doctors');
  const row = admin.getByRole('article').filter({has:admin.getByRole('heading',{name:accounts.doctor.name,exact:true})});
  await row.getByRole('button',{name:/Review|Open/}).click();
  await expect(admin.getByText(accounts.doctor.email,{exact:true})).toBeVisible();
  await admin.screenshot({path:path.join(output,'doctor-details.png'),fullPage:true});
  const evidence = admin.locator('section.panel').filter({has:admin.getByRole('heading',{name:'Credential evidence',exact:true})});
  await evidence.getByText('Record file review',{exact:true}).click();
  await evidence.getByLabel('Review / malware scan reference').fill('Synthetic automated fixture review');
  await evidence.getByRole('checkbox').check();
  const evidenceResponse = admin.waitForResponse(r=>r.url().includes('/validate/') && r.request().method()==='POST');
  await evidence.getByRole('button',{name:'Mark file reviewed and safe',exact:true}).click();
  expect((await evidenceResponse).status()).toBe(200);
  const decision = admin.locator('section.panel').filter({has:admin.getByRole('heading',{name:'Record a decision',exact:true})});
  await decision.getByLabel('Evidence reviewed').fill('Synthetic certificate');
  await decision.getByLabel('Approval reason').fill('Synthetic credential approved for test');
  await decision.getByLabel('Verification valid until').fill(new Date(Date.now()+86400000*30).toISOString().slice(0,16));
  await decision.getByRole('checkbox').check();
  const approvalResponse = admin.waitForResponse(r=>r.url().endsWith('/approve/') && r.request().method()==='POST');
  await decision.getByRole('button',{name:'Approve provider',exact:true}).click();
  expect((await approvalResponse).status()).toBe(200);
  await admin.goto(origin + '/admin/pharmacists');
  await admin.getByRole('article').filter({has:admin.getByRole('heading',{name:accounts.pharmacist.name,exact:true})}).getByRole('button',{name:'Review application'}).click();
  await admin.getByText('Reject application',{exact:true}).click();
  await admin.getByLabel('Rejection reason shown to the applicant').fill('Synthetic certificate needs correction');
  const rejectionResponse = admin.waitForResponse(r=>r.url().endsWith('/reject/') && r.request().method()==='POST');
  await admin.getByRole('button',{name:'Confirm rejection',exact:true}).click();
  expect((await rejectionResponse).status()).toBe(200);
  const approved = await json(accounts.doctor.page,'/provider/application/');
  expect(approved.current.status).toBe('approved');
  const rejected = await json(accounts.pharmacist.page,'/provider/application/');
  expect(rejected.current.status).toBe('rejected');
  expect(rejected.current.reason).toBe('Synthetic certificate needs correction');
  expect(rejected.current.reviews[0].decision).toBe('reject');
  const docAccess = await accounts.doctor.page.request.get(origin+'/api/v1/doctor/patients/');
  expect(docAccess.status()).toBe(200);
  results.push('Separate admin routes/queues, full doctor details, authenticated approval and rejection, review history and provider permission transition');
  expect(errors).toEqual([]);
  await writeFile(path.join(output,'report.json'),JSON.stringify({run,results,errors},null,2));
  console.log(results.join('\n'));
} finally { await browser.close(); }
