/** Complete synthetic UI workflow against isolated backend8001/frontend3001 only. */
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '../frontend/node_modules/@playwright/test/index.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const origin = 'http://127.0.0.1:3001';
const fixture = JSON.parse(await readFile(path.join(root, '.local/e2e-fixture.json'), 'utf8'));
const output = path.join(root, '.local/browser-workflow');
await mkdir(output, {recursive:true});
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAIAAADZF8uwAAAAF0lEQVR4nGP8//8/AyHARFDFqKIBCAIAP6kDFcAgiIsAAAAASUVORK5CYII=', 'base64');
const browser = await chromium.launch({channel:'chrome',headless:true});
const pages = {}, results = [], browserErrors = [];
const nav = (page,name) => page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
async function login(role) {
  const context = await browser.newContext({viewport:{width:1440,height:1080}});
  const page = await context.newPage(); pages[role]=page; page.setDefaultTimeout(30000);
  page.on('pageerror',error=>browserErrors.push({role,message:error.message}));
  await page.goto(origin+'/login');
  await page.locator('[name="email"]').fill(fixture.accounts[role].email);
  await page.locator('[name="password"]').fill(fixture.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await expect(page.getByText(/authenticator/i)).toHaveCount(0);
  const identity=await json(page,'/auth/me/');
  const prefix={patient:'P',doctor:'D',pharmacist:'PH',admin:'A'}[role];
  expect(identity.user.account_id).toMatch(new RegExp('^'+prefix+'-[A-HJ-NP-Z2-9]{6}$'));
  await expect(page.locator('.account-role')).toContainText(identity.user.account_id);
  results.push(role+': direct password login with cookie/CSRF sessions');
  return page;
}
async function findPatient(page,healthId,pharmacy=false) {
  await nav(page,pharmacy?'Find prescriptions':'Find patient');
  await page.getByLabel('Account ID or health card').fill(healthId);
  await page.getByRole('main').getByRole('button',{name:'Find patient',exact:true}).click();
  await expect(page.getByRole('heading',{name:fixture.accounts.patient.name,exact:true})).toBeVisible();
}
async function uploadReport(page,title,recordId) {
  await page.getByRole('button',{name:'Upload report',exact:true}).click();
  await page.locator('[name="title"]').fill(title);
  await page.locator('[name="file"]').setInputFiles({name:title+'.png',mimeType:'image/png',buffer:image});
  if(recordId) await page.locator('select[name="record_id"]').selectOption(recordId);
  await page.locator('form').getByRole('button',{name:'Upload report',exact:true}).click();
  await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
}
async function json(page,route) {
  const response=await page.request.get(origin+'/api/v1'+route);expect(response.status()).toBe(200);return response.json();
}
try {
  const patient=await login('patient');
  await expect(patient.getByRole('navigation').getByRole('button',{name:/Sharing|Access/i})).toHaveCount(0);
  await nav(patient,'My profile');
  await patient.locator('[name="date_of_birth"]').fill('1990-03-14');
  await patient.locator('[name="phone"]').fill('0000000000');
  await patient.locator('[name="emergency_contact"]').fill('Synthetic emergency contact');
  const save=patient.waitForResponse(r=>r.url().endsWith('/patients/me/')&&r.request().method()==='PATCH'&&r.status()===200);
  await patient.getByRole('button',{name:'Save profile',exact:true}).click();await save;
  const profile=await json(patient,'/patients/me/');
  expect(profile.account_id).toMatch(/^P-[A-HJ-NP-Z2-9]{6}$/);
  await nav(patient,'Health card');
  const flip=patient.getByRole('button',{name:'Flip health card',exact:true});
  await expect(flip).toHaveAttribute('aria-pressed','false');
  await patient.getByRole('button',{name:'Add photo',exact:true}).click();
  await patient.getByLabel('Patient photo',{exact:false}).setInputFiles({name:'synthetic-patient.png',mimeType:'image/png',buffer:image});
  await patient.getByRole('button',{name:'Upload photo',exact:true}).click();
  const portrait=patient.getByAltText(fixture.accounts.patient.name+"'s profile photo");
  await expect(portrait).toBeVisible();await expect(portrait).toHaveJSProperty('naturalWidth',12);
  await patient.screenshot({path:path.join(output,'health-card-front.png'),fullPage:true,animations:'disabled'});
  await flip.click();await expect(flip).toHaveAttribute('aria-pressed','true');
  await expect(patient.getByAltText('Health card QR code')).toBeVisible();
  await expect(patient.getByText('Synthetic emergency contact',{exact:true})).toBeVisible();
  await patient.screenshot({path:path.join(output,'health-card-back.png'),fullPage:true,animations:'disabled'});
  const download=patient.waitForEvent('download');
  await patient.getByRole('link',{name:'Download card',exact:true}).click();
  await (await download).saveAs(path.join(output,'health-card.pdf'));
  await patient.setViewportSize({width:390,height:844});
  await expect.poll(()=>patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await patient.screenshot({path:path.join(output,'mobile-health-card-back.png'),fullPage:true,animations:'disabled'});
  await flip.focus();await patient.keyboard.press('Enter');await expect(flip).toHaveAttribute('aria-pressed','false');
  await patient.screenshot({path:path.join(output,'mobile-health-card-front.png'),fullPage:true,animations:'disabled'});
  await patient.setViewportSize({width:1440,height:1080});
  results.push('Photo uploaded privately; health card flips by click and keyboard; mobile layout and card PDF verified');

  const doctor=await login('doctor');await findPatient(doctor,profile.account_id);
  await doctor.getByRole('button',{name:'Add consultation',exact:true}).click();
  const complaint='Synthetic consultation '+fixture.run_id;
  await doctor.getByLabel('Presenting complaint').fill(complaint);
  await doctor.getByLabel('Diagnosis',{exact:true}).fill('SYNTHETIC_CLINICAL_ONLY_DIAGNOSIS');
  await doctor.getByLabel('Consultation notes').fill('SYNTHETIC_PRIVATE_ENCOUNTER_NOTE');
  await doctor.getByRole('button',{name:'Finalize consultation',exact:true}).click();
  await expect(doctor.getByRole('heading',{name:complaint,exact:true})).toBeVisible();
  const records=await json(doctor,`/patients/${profile.id}/records/`);
  const recordId=records.results.find(r=>r.complaint===complaint).id;
  await doctor.locator('.tabs').getByRole('button',{name:'Prescriptions',exact:true}).click();
  await doctor.getByRole('button',{name:'Write prescription',exact:true}).click();
  await doctor.locator('select[name="record_id"]').selectOption(recordId);
  await doctor.getByLabel('Valid until').fill(new Date(Date.now()+3*86400000).toISOString().slice(0,16));
  await doctor.getByLabel('Medicine name').fill('Synthetic medicine '+fixture.run_id);
  await doctor.getByLabel(/^Dosage/).fill('Synthetic instructions');
  await doctor.getByLabel('Total quantity').fill('10');await doctor.getByLabel(/^Unit/).fill('tablet');
  await doctor.getByRole('button',{name:'Issue prescription',exact:true}).click();
  await expect(doctor.getByRole('button',{name:'View prescription',exact:true})).toBeVisible();
  await doctor.locator('.tabs').getByRole('button',{name:'Medical reports',exact:true}).click();
  const linkedTitle='Visit report '+fixture.run_id;
  await uploadReport(doctor,linkedTitle,recordId);
  results.push('Approved doctor finds patient without permission, saves consultation, links prescription and uploads report to visit');

  await nav(patient,'Recent visits');
  const visit=patient.getByRole('article').filter({has:patient.getByRole('heading',{name:'Dr. '+fixture.accounts.doctor.name,exact:true})}).first();
  await expect(visit).toContainText(complaint);
  await visit.locator('summary').click();
  await expect(visit).toContainText('Synthetic medicine '+fixture.run_id);
  await expect(visit).toContainText(linkedTitle);
  const reportData=await json(patient,'/patients/me/reports/');
  const linked=reportData.results.find(r=>r.title===linkedTitle);
  expect(linked.record_id).toBe(recordId);
  const reportDownload=patient.waitForEvent('download');
  await visit.getByRole('link',{name:'Download '+linkedTitle,exact:true}).click();
  await (await reportDownload).saveAs(path.join(output,'downloaded-report.png'));
  await nav(patient,'Medical reports');
  const generalTitle='General report '+fixture.run_id;
  await uploadReport(patient,generalTitle);
  await nav(patient,'Recent visits');
  await expect(patient.getByRole('heading',{name:generalTitle,exact:true})).toBeVisible();
  await patient.screenshot({path:path.join(output,'patient-visits.png'),fullPage:true,animations:'disabled'});
  await patient.reload();await expect(patient.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await nav(patient,'Recent visits');await expect(patient.getByText(complaint,{exact:true})).toBeVisible();
  await expect(patient.getByRole('heading',{name:generalTitle,exact:true})).toBeVisible();
  await patient.setViewportSize({width:390,height:844});
  await expect.poll(()=>patient.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await patient.screenshot({path:path.join(output,'mobile-patient-visits.png'),fullPage:true,animations:'disabled'});
  results.push('Recent visits show doctor, consultation, linked prescription/report; general uploaded reports and history persist after reload');

  const pharmacy=await login('pharmacist');await findPatient(pharmacy,profile.account_id,true);
  await pharmacy.getByRole('button',{name:'View prescription',exact:true}).click();
  await expect(pharmacy.getByText('SYNTHETIC_PRIVATE_ENCOUNTER_NOTE')).toHaveCount(0);
  await pharmacy.getByLabel('Synthetic medicine '+fixture.run_id+' (tablet)').fill('4');
  await pharmacy.getByRole('checkbox').check();await pharmacy.getByRole('button',{name:'Confirm dispensing',exact:true}).click();
  await expect(pharmacy.locator('tbody tr').first()).toContainText('6.000 tablet');
  for(const route of [`/patients/${profile.id}/clinical-summary/`,`/patients/${profile.id}/reports/`,`/reports/${linked.id}/download/`]) expect((await pharmacy.request.get(origin+'/api/v1'+route)).status()).toBe(403);
  await pharmacy.screenshot({path:path.join(output,'pharmacy.png'),fullPage:true,animations:'disabled'});
  results.push('Approved pharmacy finds prescriptions directly, dispenses 4/10, and cannot read full clinical history or reports');
  const admin=await login('admin');
  await expect(admin.getByRole('heading',{name:'Doctor approvals',exact:true})).toBeVisible();
  expect((await admin.request.get(origin+`/api/v1/patients/${profile.id}/clinical-summary/`)).status()).toBe(403);
  await nav(admin,'Security settings');await expect(admin.getByRole('heading',{name:'Active sessions',exact:true})).toBeVisible();
  await expect(admin.getByText(/authenticator|recovery codes/i)).toHaveCount(0);
  results.push('Admin dashboard and session settings work without authenticator; clinical access remains restricted');
  expect(browserErrors).toEqual([]);
  await writeFile(path.join(output,'results.json'),JSON.stringify({passed:true,run_id:fixture.run_id,results},null,2));
  console.log(results.map(result=>'PASS '+result).join('\n'));
} catch(error) {
  for(const [role,page] of Object.entries(pages)) {
    await page.screenshot({path:path.join(output,role+'-failure.png'),fullPage:true,animations:'disabled'}).catch(()=>{});
    await writeFile(path.join(output,role+'-failure.txt'),await page.locator('body').innerText()).catch(()=>{});
  }
  await writeFile(path.join(output,'results.json'),JSON.stringify({passed:false,results,error:error.message,browserErrors},null,2));
  throw error;
} finally { await browser.close(); }
