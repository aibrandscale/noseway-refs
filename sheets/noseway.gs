// Noseway v2 — fixed BOFU tab, date selector, durable feedback, collapsible batches.
const NW_ID='15qFvJLrxhoc5S38Dr1fFQS0Tc9RbpYpr9ZldLFUMjOM';
const NW_RAW='https://raw.githubusercontent.com/aibrandscale/noseway-refs/main/';
const NW_HEAD=['Реклама','Преглед','Копи','Одобрение','Покупки','CPA','ROAS','CPC','Spend','Статус','Корекции'];
const NW_APPROVALS=['For Review','Approved','Rework','Rejected'];
function nwBook_(){return SpreadsheetApp.openById(NW_ID);}
function nwFetch_(file,optional){
  const r=UrlFetchApp.fetch(NW_RAW+file+'?t='+Date.now(),{muteHttpExceptions:true});
  if(optional&&r.getResponseCode()===404)return {dates:{}};
  if(r.getResponseCode()!==200)throw new Error(file+' HTTP '+r.getResponseCode());
  return JSON.parse(r.getContentText());
}
function nwValidate_(data){
  if(!data||!Array.isArray(data.rows)||!data.rows.length)throw new Error('Невалиден или празен източник — данните са запазени.');
  const seen={};data.rows.forEach(r=>{
    if(!r.key||!r.name||!['meta','creative'].includes(r.kind)||seen[r.key])throw new Error('Невалиден/дублиран ред');
    seen[r.key]=true;
    if(r.kind==='creative'&&!/^https:\/\/raw\.githubusercontent\.com\/aibrandscale\/noseway-refs\//.test(r.link||''))throw new Error('Невалиден линк');
  });
}
function nwVersion_(r){return JSON.stringify([r.link||'',r.copy||'']);}
function nwSection_(e){const row=Array(14).fill('');row[0]=e.section;row[11]='section:'+e.section;row[13]=e.batch||'';return row;}
function nwDate_(v){
  if(v instanceof Date)return Utilities.formatDate(v,nwBook_().getSpreadsheetTimeZone(),'yyyy-MM-dd');
  const s=String(v||'Whole period').trim();if(s==='Whole period')return s;
  if(/^\d{4}-\d{2}-\d{2}$/.test(s))return s;
  const m=s.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{4}))?$/);
  if(!m)throw new Error('Избери Whole period или дата ДД/ММ/ГГГГ');
  const y=Number(m[3]||new Date().getFullYear()),mo=Number(m[2]),d=Number(m[1]);
  const check=new Date(Date.UTC(y,mo-1,d));
  if(check.getUTCMonth()!==mo-1||check.getUTCDate()!==d)throw new Error('Невалидна дата');
  return y+'-'+String(mo).padStart(2,'0')+'-'+String(d).padStart(2,'0');
}
function nwLabel_(iso){return iso.slice(8,10)+'/'+iso.slice(5,7)+'/'+iso.slice(0,4);}
function nwState_(book){
  let sh=book.getSheetByName('_NosewayState');
  if(!sh){sh=book.insertSheet('_NosewayState');sh.getRange(1,1,1,5).setValues([['key','approval','corrections','version','status']]);sh.hideSheet();}
  const values=sh.getLastRow()>1?sh.getRange(2,1,sh.getLastRow()-1,5).getValues():[];
  const state={};values.forEach(r=>state[r[0]]={approval:r[1],fix:r[2],version:r[3],status:r[4]});return {sh,state};
}
function nwStore_(db){
  const rows=Object.keys(db.state).map(k=>{const v=db.state[k];return [k,v.approval,v.fix,v.version,v.status||'On hold'];});
  if(rows.length)db.sh.getRange(2,1,rows.length,5).setValues(rows);
  SpreadsheetApp.flush();
}
function nwCapture_(sh,db,source){
  const n=sh.getLastRow();if(n<3)return;
  const vals=sh.getRange(1,1,n,14).getValues(),notes=sh.getRange(1,4,n,1).getNotes();
  const byName={};source.forEach(r=>byName[r.name]=r);
  vals.forEach((v,i)=>{
    if(!NW_APPROVALS.includes(v[3]))return;
    const old=byName[String(v[0]).trim()],key=v[11]||(old&&old.key);if(!key)return;
    let ver=v[12];
    if(!ver&&old)ver=JSON.stringify([notes[i][0]||old.link,v[2]||'']);
    db.state[key]={approval:v[3],fix:v[10]||'',version:ver||'',status:v[9]||'On hold'};
  });
}
function syncNoseway(){
  const lock=LockService.getScriptLock();if(!lock.tryLock(25000))return;
  try{
    const data=nwFetch_('sheet.json');nwValidate_(data);
    const daily=nwFetch_('metrics_daily.json',true);
    const book=nwBook_(),sh=book.getSheetByName('BOFU');if(!sh)throw new Error('Липсва BOFU');
    const initialized=sh.getRange('L1').getValue()==='noseway-v2';
    const selected=initialized?nwDate_(sh.getRange('B2').getValue()):'Whole period';
    const db=nwState_(book);nwCapture_(sh,db,data.rows);nwStore_(db);
    const entries=[],groups=[],meta=data.rows.filter(r=>r.kind==='meta'),batches={};
    data.rows.filter(r=>r.kind==='creative').forEach(r=>{const b=r.batch_id||'batch-legacy-001';(batches[b]||(batches[b]=[])).push(r);});
    entries.push({section:'Meta реклами · '+(selected==='Whole period'?'Whole period':nwLabel_(selected))});
    const day=selected==='Whole period'?null:(daily.dates||{})[selected];
    const dayReady=!!(day&&day.complete===true&&Array.isArray(day.rows));
    const dayMap={};if(dayReady)day.rows.forEach(r=>dayMap[r.key]=r);
    meta.forEach(r=>entries.push({row:r,metrics:selected==='Whole period'?r:(dayReady?(dayMap[r.key]||{results:0,spend:0}):{})}));
    Object.keys(batches).sort((a,b)=>a==='batch-legacy-001'?-1:b==='batch-legacy-001'?1:a.localeCompare(b)).forEach((id,index)=>{
      const rs=batches[id],dates=rs.map(r=>(r.created_at||(r.link.match(/creatives-(\d{4}-\d{2}-\d{2})/)||[])[1]||'').slice(0,10)).filter(Boolean).sort();
      const date=dates.length?nwLabel_(dates[0]):'';
      entries.push({section:'Batch '+String(index+1).padStart(2,'0')+' · '+date+' · '+rs.length+' креатива',batch:id});
      const start=entries.length+5;rs.forEach(r=>entries.push({row:r}));groups.push({id,start,count:rs.length});
    });
    const body=entries.map(e=>{
      if(e.section)return nwSection_(e);
      const r=e.row,m=e.metrics||{},v=nwVersion_(r);let approval='—',fix='—';
      if(r.kind==='creative'){
        const prev=db.state[r.key];const changed=prev&&prev.version!==v;
        approval=changed?'For Review':(prev&&prev.approval)||'For Review';
        fix=changed?'':(prev&&prev.fix)||'';
        db.state[r.key]={approval,fix,version:v,status:r.status||'On hold'};
      }
      return [r.name,'',r.copy||'',approval,m.results??'',m.cpa??'',m.roas??'',m.cpc??'',m.spend??'',r.status||'On hold',fix,r.key,v,r.batch_id||'batch-legacy-001'];
    });
    const oldLast=Math.max(sh.getLastRow(),5),oldKeys=initialized?sh.getRange(5,12,oldLast-4,1).getValues().flat():[];
    const structural=JSON.stringify(oldKeys)!==JSON.stringify(body.map(r=>r[11]));
    const collapsed={};if(initialized)for(let i=5;i<=oldLast;i++){
      if(sh.getRowGroupDepth(i)>0){const g=sh.getRowGroup(i,1),id=sh.getRange(i,14).getValue();collapsed[id]=g.isCollapsed();i=g.getRange().getLastRow();}
    }
    if(sh.getMaxRows()<body.length+4)sh.insertRowsAfter(sh.getMaxRows(),body.length+4-sh.getMaxRows());
    if(structural){
      sh.getRange(1,1,Math.max(oldLast,body.length+4),14).breakApart();
      if(initialized)sh.getRange(5,1,oldLast-4,14).shiftRowGroupDepth(-8);
      sh.getRange(1,1,Math.max(oldLast,body.length+4),14).clearDataValidations();
      // Durable state was flushed above. Build all values before touching layout.
      if(oldLast>body.length+4)sh.getRange(body.length+5,1,oldLast-body.length-4,14).clearContent();
    }
    sh.getRange(5,1,body.length,14).setValues(body);
    sh.getRange(5,1,body.length,11).clearFormat().clearNote();
    sh.getRange('L1').setValue('noseway-v2');
    sh.getRange('A1:K1').merge().setValue('NOSEWAY · BOFU РЕКЛАМИ').setBackground('#163343').setFontColor('#ffffff').setFontSize(16).setFontWeight('bold');
    sh.getRange('A2').setValue('Период');
    sh.getRange('A2:K3').setBackground('#ffffff').setFontColor('#243748').setFontWeight('normal').setHorizontalAlignment('left');
    const options=['Whole period',...Object.keys(daily.dates||{}).sort().reverse().map(nwLabel_)];
    sh.getRange('B2').setNumberFormat('@').setValue(selected==='Whole period'?selected:nwLabel_(selected)).setBackground('#dce7fb').setFontColor('#163343').setFontWeight('bold')
      .setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(options,true).setAllowInvalid(true).build())
      .setNote('Whole period = целият период. Дата: ДД/ММ или ДД/ММ/ГГГГ. Дневните данни са по часовата зона на Meta акаунта.');
    sh.getRange('C2:K2').merge().setValue('Източник: '+data.updated_at+' · '+(daily.account_timezone||'Часова зона: Meta акаунт')).setFontSize(9);
    sh.getRange('A3:K3').merge().setValue(selected!=='Whole period'&&!dayReady?'Данните за избраната дата още се зареждат. Проверка през 30 минути.':'Одобренията и корекциите се пазят. Свий/разгъни Batch със стрелката вляво.').setFontSize(10).setFontColor('#526579');
    sh.getRange(4,1,1,11).setValues([NW_HEAD]).setBackground('#2b52a1').setFontColor('#ffffff').setFontWeight('bold');
    sh.getRange(1,1,body.length+4,11).setFontFamily('Arial').setVerticalAlignment('middle');
    sh.setFrozenRows(4);sh.setRowHeight(1,42);sh.setRowHeights(2,3,30);
    [210,150,340,125,80,82,75,82,90,100,300].forEach((w,i)=>sh.setColumnWidth(i+1,w));
    sh.hideColumns(12,3);
    const apprRule=SpreadsheetApp.newDataValidation().requireValueInList(NW_APPROVALS,true).setAllowInvalid(false).build();
    entries.forEach((e,i)=>{
      const n=i+5,range=sh.getRange(n,1,1,11);
      if(e.section){range.merge().setBackground('#dce7fb').setFontColor('#163343').setFontWeight('bold');sh.getRange(n,1).setRichTextValue(SpreadsheetApp.newRichTextValue().setText(e.section).build());sh.setRowHeight(n,34);return;}
      const r=e.row;range.setBackground(i%2?'#ffffff':'#f3f6fa').setFontColor('#243748').setFontSize(10).setFontWeight('normal');
      sh.setRowHeight(n,r.kind==='creative'?150:32);
      sh.getRange(n,3).setWrap(true).setVerticalAlignment('top').setFontSize(9);
      sh.getRange(n,11).setWrap(true).setVerticalAlignment('top').setFontSize(10);
      if(r.link){
        sh.getRange(n,2).setFormula('=IMAGE("'+r.link+'")');
        sh.getRange(n,1).setRichTextValue(SpreadsheetApp.newRichTextValue().setText(r.name).setLinkUrl(r.link).build());
        sh.getRange(n,4).setDataValidation(apprRule).setNote(r.link);
      }else{sh.getRange(n,1).setRichTextValue(SpreadsheetApp.newRichTextValue().setText(r.name).build()).setNote('Meta ad ID: '+r.key);sh.getRange(n,2).setValue('—');sh.getRange(n,4).clearDataValidations();}
      sh.getRange(n,5).setNumberFormat('0');[6,8,9].forEach(c=>sh.getRange(n,c).setNumberFormat('$#,##0.00'));sh.getRange(n,7).setNumberFormat('0.00');
    });
    if(structural){
      sh.setRowGroupControlPosition(SpreadsheetApp.GroupControlTogglePosition.BEFORE);
      groups.forEach(g=>{if(g.count){sh.getRange(g.start,1,g.count,11).shiftRowGroupDepth(1);if(collapsed[g.id])sh.getRowGroup(g.start,1).collapse();}});
    }
    sh.setConditionalFormatRules(NW_APPROVALS.map((a,i)=>SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo(a)
       .setBackground(['#dce7fb','#d6f0dd','#ffe8cc','#f8d7da'][i]).setRanges([sh.getRange(5,4,body.length,1)]).build()));
    nwStore_(db);sh.getRange('A1').setNote('Синхронизация: '+new Date().toISOString()+'\nИзточник: '+data.updated_at);
  }finally{lock.releaseLock();}
}
function nosewayEdit(e){
  if(!e||e.range.getSheet().getName()!=='BOFU')return;
  if(e.range.getA1Notation()==='B2'){syncNoseway();return;}
  if(e.range.getLastRow()<5||e.range.getColumn()>11||e.range.getLastColumn()<4)return;
  const lock=LockService.getScriptLock();lock.waitLock(25000);
  try{const sh=e.range.getSheet(),db=nwState_(nwBook_());
    for(let n=Math.max(e.range.getRow(),5);n<=e.range.getLastRow();n++){
      const row=sh.getRange(n,1,1,14).getValues()[0];
      if(row[11]&&NW_APPROVALS.includes(row[3]))db.state[row[11]]={approval:row[3],fix:row[10]||'',version:row[12],status:row[9]};
    }nwStore_(db);
  }finally{lock.releaseLock();}
}
function onEdit(e){} // The old simple handler is intentionally replaced by the installed handler.
function onOpen(){SpreadsheetApp.getUi().createMenu('Noseway').addItem('Обнови сега','syncNoseway').addToUi();}
function setupAll(){
  syncNoseway();
  ScriptApp.getProjectTriggers().filter(t=>['syncNoseway','nosewayEdit','onEdit'].includes(t.getHandlerFunction())).forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('syncNoseway').timeBased().everyMinutes(30).create();
  ScriptApp.newTrigger('nosewayEdit').forSpreadsheet(NW_ID).onEdit().create();
}
