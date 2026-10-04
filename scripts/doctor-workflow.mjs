/** Doctor dashboard integration checks. Run browser-workflow.mjs first on the same isolated fixture. */
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '../frontend/node_modules/@playwright/test/index.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const origin='http://127.0.0.1:3001';
const fixture=JSON.parse(await readFile(path.join(root,'.local/e2e-fixture.json'),'utf8'));
const output=path.join(root,'.local/doctor-workflow');
await mkdir(output,{recursive:true});
const pages={}, results=[], errors=[];
let browser;
const nav=(page,name)=>page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
async function login(key, camera=false) {
  const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:camera?['camera']:[]});
  const page=await context.newPage();pages[key]=page;page.setDefaultTimeout(30000);
  if(camera) await page.addInitScript(()=>{
    window.testCameraTracks=[];
    const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=async constraints=>{
      const stream=await original(constraints);window.testCameraTracks.push(...stream.getTracks());return stream;
    };
  });
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin+'/login');
  await page.locator('[name="email"]').fill(fixture.accounts[key].email);
  await page.locator('[name="password"]').fill(fixture.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  return page;
}
async function api(page,route,method='GET',data) {
  const headers={};
  if(method!=='GET') {
    const token=await page.request.get(origin+'/api/v1/auth/csrf/');
    headers['X-CSRFToken']=(await token.json()).csrfToken;
    headers['Origin']=origin;
  }
  const response=await page.request.fetch(origin+'/api/v1'+route,{method,headers,data});
  return {status:response.status(),body:await response.json().catch(()=>null)};
}
async function get(page,route) {const response=await api(page,route);expect(response.status).toBe(200);return response.body;}
async function saveScreenshot(page,name) {await page.screenshot({path:path.join(output,name+'.png'),fullPage:true,animations:'disabled'});}
try {
  browser=await chromium.launch({channel:'chrome',headless:true});
  const patient=await login('patient');
  const profile=await get(patient,'/patients/me/');
  const card=await get(patient,'/patients/me/card/');
  const qrPath=path.join(output,'patient-qr.png');
  await writeFile(qrPath,Buffer.from(card.qr_data_url.split(',')[1],'base64'));
  await browser.close();
  const videoPath=path.join(output,'synthetic-qr-camera.y4m');
  const cameraPython = String.raw`from PIL import Image
import sys
source = Image.open(sys.argv[1]).convert("RGB")
with open(sys.argv[2], "wb") as target:
    target.write(b"YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg" + bytes([10]))
    for size in [225, 270, 315, 360, 315, 270]:
        canvas = Image.new("RGB", (640, 480), "white")
        canvas.paste(source.resize((size, size), Image.Resampling.NEAREST), ((640-size)//2, (480-size)//2))
        y, u, v = canvas.convert("YCbCr").split()
        frame = y.tobytes() + u.resize((320,240), Image.Resampling.BOX).tobytes() + v.resize((320,240), Image.Resampling.BOX).tobytes()
        for _ in range(5):
            target.write(b"FRAME" + bytes([10]) + frame)
`;
  const py=spawnSync(path.join(root,'.venv/Scripts/python.exe'),['-c',cameraPython,qrPath,videoPath],{encoding:'utf8',windowsHide:true});
  if(py.status!==0) throw new Error('Synthetic camera fixture failed: '+py.stderr);
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-video-capture='+videoPath]});
  const doctor=await login('second_doctor',true);
  expect((await get(doctor,'/doctor/patients/')).results).toEqual([]);
  await nav(doctor,'Find patient');
  await doctor.getByRole('button',{name:'Scan QR with camera',exact:true}).click();
  await expect(doctor.getByRole('heading',{name:profile.name,exact:true})).toBeVisible({timeout:15000});
  await expect.poll(()=>doctor.evaluate(()=>window.testCameraTracks.length>0&&window.testCameraTracks.every(track=>track.readyState==='ended'))).toBeTruthy();
  expect((await get(doctor,'/doctor/patients/')).results).toEqual([]);
  results.push('Camera decodes the patient health-card QR and opens history automatically; camera tracks stop; lookup does not save patient');
  const originalComplaint='Synthetic consultation '+fixture.run_id;
  const earlier=doctor.locator('.timeline-item').filter({has:doctor.getByRole('heading',{name:originalComplaint,exact:true})});
  await expect(earlier).toBeVisible();
  await expect(earlier).toContainText(fixture.accounts.doctor.name);
  await expect(earlier.getByText(/Add correction|Correct record/)).toHaveCount(0);
  const records=await get(doctor,`/patients/${profile.id}/records/`);
  const original=records.results.find(item=>item.complaint===originalComplaint);
  expect(original.doctor_id).toBe(fixture.accounts.doctor.id);
  const denied=await api(doctor,`/records/${original.id}/corrections/`,'POST',{complaint:'Forbidden edit',notes:'Must not save',correction_reason:'Not the author'});
  expect(denied.status).toBe(403);
  expect((await api(doctor,`/patients/${profile.id}/records/`,'PATCH',{complaint:'Forbidden edit'})).status).toBe(405);
  await doctor.locator('.tabs').getByRole('button',{name:'Medical reports',exact:true}).click();
  const oldTitle='Visit report '+fixture.run_id;
  await expect(doctor.getByRole('heading',{name:oldTitle,exact:true})).toBeVisible();
  const oldReport=(await get(doctor,`/patients/${profile.id}/reports/`)).results.find(report=>report.title===oldTitle);
  expect((await doctor.request.get(origin+oldReport.download_url)).status()).toBe(200);
  expect((await api(doctor,`/reports/${oldReport.id}/download/`,'DELETE')).status).toBe(405);
  results.push('Other doctor consultations, prescriptions and private reports readable; cross-author correction and edit/delete attempts rejected');
  await doctor.getByRole('button',{name:'Add patient',exact:true}).click();
  await expect(doctor.getByText('Added to My patients',{exact:true})).toBeVisible();
  const saved=await get(doctor,'/doctor/patients/');
  expect(saved.results.filter(item=>item.id===profile.id)).toHaveLength(1);
  const addedAgain=await api(doctor,`/doctor/patients/${profile.id}/`,'POST',{});
  expect([200,201]).toContain(addedAgain.status);
  expect((await get(doctor,'/doctor/patients/')).results.filter(item=>item.id===profile.id)).toHaveLength(1);
  await nav(doctor,'My patients');
  await expect(doctor.getByRole('heading',{name:profile.name,exact:true})).toBeVisible();
  await saveScreenshot(doctor,'my-patients');
  await doctor.reload();await expect(doctor.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await nav(doctor,'My patients');
  await doctor.getByRole('button',{name:'Open record',exact:true}).click();
  await expect(doctor.getByText('Added to My patients',{exact:true})).toBeVisible();
  await doctor.getByRole('button',{name:'View My patients',exact:true}).click();
  await doctor.getByRole('button',{name:'Open record',exact:true}).click();
  await doctor.getByRole('button',{name:'Add consultation',exact:true}).click();
  const newComplaint='New doctor consultation '+fixture.run_id;
  await doctor.getByLabel('Presenting complaint').fill(newComplaint);
  await doctor.getByLabel('Diagnosis',{exact:true}).fill('SYNTHETIC_NEW_DIAGNOSIS');
  await doctor.getByLabel('Consultation notes').fill('A new consultation. Previous records remain unchanged.');
  await doctor.getByRole('button',{name:'Finalize consultation',exact:true}).click();
  await expect(doctor.getByRole('heading',{name:newComplaint,exact:true})).toBeVisible();
  const updatedRecords=await get(doctor,`/patients/${profile.id}/records/`);
  expect(updatedRecords.results.find(item=>item.id===original.id)).toEqual(original);
  const newRecord=updatedRecords.results.find(item=>item.complaint===newComplaint);
  await doctor.locator('.tabs').getByRole('button',{name:'Medical reports',exact:true}).click();
  await doctor.getByRole('button',{name:'Upload report',exact:true}).click();
  const newTitle='Second doctor report '+fixture.run_id;
  await doctor.locator('[name="title"]').fill(newTitle);
  await doctor.locator('[name="file"]').setInputFiles(qrPath);
  await doctor.locator('select[name="record_id"]').selectOption(newRecord.id);
  await doctor.locator('form').getByRole('button',{name:'Upload report',exact:true}).click();
  await expect(doctor.getByRole('heading',{name:newTitle,exact:true})).toBeVisible();
  await expect(doctor.getByRole('heading',{name:oldTitle,exact:true})).toBeVisible();
  await saveScreenshot(doctor,'combined-reports');
  const firstDoctor=await login('doctor');
  expect((await get(firstDoctor,'/doctor/patients/')).results).toEqual([]);
  results.push('Add patient is idempotent and persists in only this doctor’s My patients; new consultation/report leaves earlier history unchanged');
  await nav(doctor,'Find patient');
  await doctor.getByLabel('Account ID or health card').fill(profile.account_id.toLowerCase());
  await doctor.getByRole('main').getByRole('button',{name:'Find patient',exact:true}).click();
  await expect(doctor.getByRole('heading',{name:profile.name,exact:true})).toBeVisible();
  results.push('Lowercase compact patient ID opens the same history as the camera QR');
  await nav(doctor,'My profile');
  const originalId=fixture.accounts.second_doctor.account_id;
  await doctor.locator('[name="name"]').fill('Updated synthetic doctor '+fixture.run_id);
  await doctor.locator('[name="phone"]').fill('0000000000');
  await doctor.getByRole('button',{name:'Save profile',exact:true}).click();
  await expect.poll(async()=> (await get(doctor,'/doctor/profile/')).user.name).toBe('Updated synthetic doctor '+fixture.run_id);
  const updated=await get(doctor,'/doctor/profile/');
  expect(updated.user.account_id).toBe(originalId);expect(updated.user.phone).toBe('0000000000');
  const identityChange=await api(doctor,'/doctor/profile/','PATCH',{email:'changed@example.test',account_id:'D-AAAAAA',role:'admin'});
  expect(identityChange.status).toBe(400);
  await doctor.reload();await expect(doctor.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await nav(doctor,'My profile');await expect(doctor.locator('[name="name"]')).toHaveValue(updated.user.name);
  await saveScreenshot(doctor,'doctor-profile');
  await nav(doctor,'Security settings');
  await expect(doctor.getByRole('heading',{name:'Active sessions',exact:true})).toBeVisible();
  await expect(doctor.getByRole('button',{name:'Send password reset email',exact:true})).toBeVisible();
  await expect(doctor.getByText(/authenticator/i)).toHaveCount(0);
  await doctor.setViewportSize({width:390,height:844});
  await nav(doctor,'My patients');
  await expect(doctor.getByRole('button',{name:'Open record',exact:true})).toBeVisible();
  await expect.poll(()=>doctor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await saveScreenshot(doctor,'mobile-my-patients');
  await nav(doctor,'My profile');
  await expect(doctor.getByRole('heading',{name:'Personal details',exact:true})).toBeVisible();
  await expect.poll(()=>doctor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await saveScreenshot(doctor,'mobile-doctor-profile');
  results.push('Doctor profile name/phone persist; account identity protected; shared security/password/session controls and mobile layout verified');
  expect(errors).toEqual([]);
  await writeFile(path.join(output,'results.json'),JSON.stringify({passed:true,run_id:fixture.run_id,results},null,2));
  console.log(results.map(result=>'PASS '+result).join('\n'));
} catch(error) {
  for(const [key,page] of Object.entries(pages)) if(!page.isClosed()) {
    await saveScreenshot(page,key+'-failure').catch(()=>{});
    await writeFile(path.join(output,key+'-failure.txt'),await page.locator('body').innerText()).catch(()=>{});
  }
  await writeFile(path.join(output,'results.json'),JSON.stringify({passed:false,results,error:error.message,errors},null,2));
  throw error;
} finally {await browser?.close();}
