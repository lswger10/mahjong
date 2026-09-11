// Permanent real-browser / TCP acceptance. Only synthetic local rooms; no model calls.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import http from 'node:http';
import net from 'node:net';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort() { const s = net.createServer(); await new Promise(r => s.listen(0, '127.0.0.1', r)); const port=s.address().port; await new Promise(r=>s.close(r)); return port; }
const port = await freePort(), mcpPort = await freePort();
const data = mkdtempSync(path.join(tmpdir(), 'mahjong-browser-'));
let processHandle, browser, proxy;
let logs = '';
async function start() {
  const python = process.env.MAHJONG_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  processHandle = spawn(python, ['-X','utf8','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',String(port),'--no-access-log'],
    {cwd:root, windowsHide:true, env:{...process.env, MAHJONG_DATA_DIR:data, MAHJONG_MCP_PORT:String(mcpPort), PYTHONUNBUFFERED:'1'}});
  processHandle.stderr.on('data',d=>logs+=d);
  processHandle.stdout.on('data',d=>logs+=d);
  for(let n=0;n<100;n++) {
    try { if((await fetch(`http://127.0.0.1:${port}/healthz`)).ok) return; } catch {}
    if(processHandle.exitCode !== null) throw new Error('Local test server exited: '+logs);
    await sleep(100);
  }
  throw new Error('Local test server startup timeout: '+logs);
}
async function stop() {
  if (!processHandle || processHandle.exitCode !== null) return;
  const child=processHandle;
  if(process.platform==='win32') execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  else child.kill('SIGTERM');
  for(let n=0;n<50 && child.exitCode===null;n++) await sleep(100);
}

try {
  await start();
  // Native test-only prefix proxy exercises /mahjong/ URLs and WS upgrades.
  proxy=http.createServer((req,res)=>{
    if(req.url.startsWith('/mahjong/')) {
      const upstream=http.request({host:'127.0.0.1',port,path:req.url.slice('/mahjong'.length),method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
      upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);return;
    }
    if(process.env.TIDAL_WEB_ROOT && req.url.startsWith('/chat/')) {
      const name=path.basename(new URL(req.url,'http://test').pathname);
      try { const bytes=readFileSync(path.join(process.env.TIDAL_WEB_ROOT,name));res.setHeader('Content-Type',name.endsWith('.html')?'text/html':name.endsWith('.js')?'application/javascript':'application/octet-stream');res.end(bytes);return;}catch{}
    }
    res.writeHead(404);res.end();
  });
  proxy.on('upgrade',(req,socket,head)=>{
    if(!req.url.startsWith('/mahjong/ws/')) {socket.destroy();return;}
    const upstream=http.request({host:'127.0.0.1',port,path:req.url.slice('/mahjong'.length),headers:req.headers});
    upstream.on('upgrade',(response,target,targetHead)=>{
      socket.write(`HTTP/1.1 101 Switching Protocols\r\n${Object.entries(response.headers).map(([k,v])=>`${k}: ${v}`).join('\r\n')}\r\n\r\n`);
      if(head.length)target.write(head);if(targetHead.length)socket.write(targetHead);
      target.on('error',()=>socket.destroy());socket.on('error',()=>target.destroy());target.pipe(socket);socket.pipe(target);
    });upstream.on('error',()=>socket.destroy());upstream.end();
  });
  await new Promise(r=>proxy.listen(0,'127.0.0.1',r));
  const origin=`http://127.0.0.1:${proxy.address().port}`;
  browser=await chromium.launch({channel:'msedge',headless:true});
  const first=await browser.newContext(), second=await browser.newContext({viewport:{width:412,height:915},isMobile:true,hasTouch:true});
  const a=await first.newPage(), b=await second.newPage(), errors=[];
  for(const page of [a,b])page.on('pageerror',error=>errors.push(error.message));
  if(process.env.TIDAL_WEB_ROOT) {
    await a.goto(origin+'/chat/entertainment.html');await a.locator('#openMahjong').click();
    await a.frameLocator('#table').locator('#btn-create-room').waitFor();
    await a.frameLocator('#table').locator('#back-entertainment').click();
    await a.locator('#table').waitFor({state:'detached'});
  }
  await a.goto(origin+'/mahjong/');await a.locator('#nickname').fill('薇薇测试');
  a.once('dialog',d=>d.accept('浏览器人工牌桌'));await a.locator('#btn-create-room').click();await a.waitForURL('**/game.html?room=*');
  const rid=new URL(a.url()).searchParams.get('room');
  await b.goto(origin+'/mahjong/?join='+rid);await b.locator('#nickname').fill('朋友测试');await b.locator('#btn-join-room').click();await b.waitForURL('**/game.html?room=*');
  await a.locator('#btn-start').click();
  for(const page of [a,b]) await page.waitForFunction(()=>gameState?.players?.length===4);
  const va=await a.evaluate(()=>({id:PLAYER_ID,idx:myPlayerIdx,state:gameState}));
  const vb=await b.evaluate(()=>({id:PLAYER_ID,idx:myPlayerIdx,state:gameState}));
  assert.notEqual(va.id,vb.id);assert.equal(va.idx,0);assert.equal(vb.idx,1);
  assert(!va.state.players[0].hand.hidden && va.state.players[1].hand.hidden);
  assert(!vb.state.players[1].hand.hidden && vb.state.players[0].hand.hidden);
  // Regression: owner may restart even when the next dealer is another human.
  for (const page of [a,b]) await page.evaluate(()=>{
    handleGameOver({winner_idx:null,scores:{},cumulative_scores:{},next_dealer_idx:1,is_reconnect:false});
  });
  assert.equal(await a.locator('#btn-play-again').isEnabled(),true);
  assert.equal(await b.locator('#btn-play-again').isEnabled(),false);
  for (const page of [a,b]) await page.evaluate(()=>document.getElementById('game-over-modal').classList.add('hidden'));
  assert(!(await a.evaluate(()=>document.cookie)).includes('mahjong_guest'));
  assert((await first.cookies()).find(c=>c.name==='mahjong_guest').httpOnly);
  const other=(await (await first.request.post(origin+'/mahjong/api/rooms',{data:{name:'隔离房间'}})).json()).id;
  assert.equal((await second.request.get(origin+'/mahjong/api/rooms/'+other)).status(),403);
  const spoof=await second.request.post(origin+'/mahjong/api/rooms/'+rid+'/action',{data:{type:'discard',revision:va.state.revision,player_id:va.id,tile:va.state.players[0].hand.tiles[0]}});
  assert.equal(spoof.status(),400);
  await a.locator('#my-hand .tile[data-tile]').first().click();await a.locator('#btn-discard').click();
  // AI claims may legally skip the next seat. Wait for a stable human turn,
  // responding only to each authenticated guest's own pending claim.
  let stable;
  for(let n=0;n<200;n++) {
    const state=await (await second.request.get(origin+'/mahjong/api/rooms/'+rid)).json();
    if(state.revision>va.state.revision && state.state.phase==='discarding' && state.state.current_turn<2) {stable=state;break;}
    if(state.room.status==='ended') {stable=state;break;}
    for(const context of [first,second]) {
      const own=await (await context.request.get(origin+'/mahjong/api/rooms/'+rid)).json();
      if(own.state.available_actions.includes('skip'))await context.request.post(origin+'/mahjong/api/rooms/'+rid+'/action',{data:{type:'skip',revision:own.revision}});
    }
    await sleep(100);
  }
  assert(stable,'table did not reach a stable human turn after the real UI discard');
  await b.waitForFunction(revision=>gameState.revision>=revision,stable.revision);
  const restoredBefore=await (await second.request.get(origin+'/mahjong/api/rooms/'+rid)).json();
  await a.close();await b.reload();await b.waitForFunction(()=>gameState?.players?.length===4);
  assert.equal(await b.evaluate(()=>PLAYER_ID),vb.id);
  assert.equal((await (await first.request.get(origin+'/mahjong/api/rooms/'+other)).json()).room.status,'waiting');
  await b.screenshot({path:path.join(data,'mobile.png')});
  // Restart the isolated test process; the browser cookie and seat must remain usable.
  await stop();await start();await b.reload();await b.waitForFunction(()=>gameState?.players?.length===4);
  assert.equal(await b.evaluate(()=>PLAYER_ID),vb.id);
  assert.deepEqual((await (await second.request.get(origin+'/mahjong/api/rooms/'+rid)).json()).state.players[1].hand,restoredBefore.state.players[1].hand);

  const metadata={'openai/subject':'browser-test','openai/session':'browser-response','openai/organization':'synthetic'};
  async function mcp(method,params={}) {
    const r=await fetch(`http://127.0.0.1:${mcpPort}/mcp`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json, text/event-stream'},body:JSON.stringify({jsonrpc:'2.0',id:randomUUID(),method,params})});
    assert.equal(r.status,200);return (await r.json()).result;
  }
  assert.equal((await fetch(`http://127.0.0.1:${port}/mcp`,{method:'POST'})).status,405);
  assert.equal((await fetch(`http://127.0.0.1:${mcpPort}/mcp`,{method:'POST',headers:{Origin:'http://evil.invalid'}})).status,403);
  assert.equal((await mcp('tools/list')).tools.length,5);
  const joined=await mcp('tools/call',{name:'join_table',arguments:{room_code:other,instance_id:randomUUID()},_meta:metadata});
  assert(!joined.isError,JSON.stringify(joined));assert.equal((joined.structuredContent || JSON.parse(joined.content[0].text)).player_idx,1);
  assert.equal((await (await first.request.get(origin+'/mahjong/api/rooms/'+other)).json()).seats[1].kind,'external_agent');
  assert.deepEqual(errors,[]);
  if(process.env.MAHJONG_SCREENSHOT) {
    const {copyFileSync}=await import('node:fs');copyFileSync(path.join(data,'mobile.png'),process.env.MAHJONG_SCREENSHOT);
  }
  console.log(JSON.stringify({ok:true,checks:['two browser guests','private HTTP and WS hands','identity spoof denied','room isolation','real UI discard','mobile reload','process restart recovery','private TCP MCP tools and join','public MCP blocked','no page errors',...(process.env.TIDAL_WEB_ROOT?['Tidal entertainment entry and return']:[])]}));
} catch (error) {
  console.error('Browser test failure:', error, logs);
  throw error;
} finally {
  if(browser)await browser.close();
  if(proxy){proxy.closeAllConnections();proxy.close();}
  await stop();
  const resolved=path.resolve(data);
  assert(resolved.startsWith(path.resolve(tmpdir())+path.sep) && path.basename(resolved).startsWith('mahjong-browser-'));
  rmSync(resolved,{recursive:true,force:true});
}
