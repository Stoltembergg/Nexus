const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {EventEmitter} = require('node:events');
const source = fs.readFileSync(__dirname + '/riot-league-update-hook.js', 'utf8');
async function scenario(options = {}) {
  let callback; const writes = []; const sieveRequests = [];
  const install = state => ({status:{patch:{state,tags:['en_GB'],url:options.recordedUrl || ''}},requests:{patch:null}});
  const installs = {client:install(options.client || 'out_of_date'),game:install(options.game || 'up_to_date')};
  if (options.active) installs[options.active].requests.patch = {};
  if(options.legacyRoot) Object.assign(installs.game,{path:'/Applications/League of Legends.app/Game',metadata_path:'/fixture/game',seed_path:'/fixture/seed',excluded_paths:['keep'],ipv4_only:false});
  const manifest = options.url || 'https://lol.secure.dyn.riotcdn.net/channels/public/releases/66B91DB25E5AD56E.manifest';
  const metadata = {patch_url:manifest,tags:[],content_cookies:options.cookies || []};
  const config = {public:[{data:{'keystone.products.league_of_legends.patchlines.live':{
    platforms:{mac:{configurations:[{secondary_patchlines:[{id:'game_patch',url:'https://lol.secure.dyn.riotcdn.net/channels/public/releases/BAA127646F53294E.manifest'}]}]}}
  }}}]};
  const https = {Agent:class {},request(config,receive) {
    const req = new EventEmitter(); req.setTimeout = () => {}; req.destroy = () => {};
    req.end = body => queueMicrotask(() => {
      let data = null;
      if (config.hostname === 'sieve.services.riotcdn.net') {
        sieveRequests.push(config.path);
        if (options.sieveDown) {const bad = new EventEmitter(); bad.statusCode=503; receive(bad); bad.emit('end'); return;}
        data={releases:[{release:{created_at:'2026-01-01T00:00:00Z'},download:{url:'https://lol.secure.dyn.riotcdn.net/channels/public/releases/AAAAAAAAAAAAAAAA.manifest',scd_required:false}},
          {release:{created_at:'2026-10-02T21:05:04Z'},download:{url:manifest,scd_required:false}}]};
      } else if (config.path === '/riotclient/region-locale') data={region:options.region || 'EUW',locale:'en_GB'};
      else if (config.method === 'PUT') {
        writes.push({path:config.path,body:JSON.parse(body)});
        if (config.path === '/patch/v1/installs/league_of_legends.live.game_patch') {
          Object.assign(installs.game, JSON.parse(body));
        }
        if (config.path.includes('/requests/patch') && options.retainRequest) {
          installs[config.path.includes('game_patch') ? 'game':'client'].requests.patch=JSON.parse(body);
        }
        if (config.path.includes('/requests/patch') && !options.unfinished) {
          installs[config.path.includes('game_patch') ? 'game':'client'].status.patch.state='up_to_date';
        }
      } else if(config.method === 'DELETE') {
        writes.push({path:config.path,method:'DELETE'});
        installs[config.path.includes('game_patch') ? 'game':'client'].requests.patch=null;
      } else if (config.path.startsWith('/product-metadata')) data=metadata;
      else if (config.path.startsWith('/product-integration-deps')) data={updateAvailable:!!options.stale};
      else data=installs[config.path.includes('game_patch') ? 'game':'client'];
      const response = new EventEmitter(); response.statusCode=200; receive(response);
      response.emit('data',JSON.stringify(data)); response.emit('end');
    }); return req;
  }};
  const electron={app:{getName:()=> 'Riot Client'},session:{defaultSession:{webRequest:{onCompleted:(_filter,fn)=>callback=fn}}}};
  const modules={electron,https,fs:{existsSync:()=>!!options.nativeGame,readFileSync:p=>p.endsWith('.json') ? JSON.stringify(config):Buffer.from('owned-fixture-ca')},path:require('node:path')};
  const context={process:{argv:['test','--app-port=12345','--remoting-auth-token=owned-fixture'],mainModule:{filename:'/fixture/main.js',require:name=>modules[name]}},Buffer,URL,setTimeout:fn=>queueMicrotask(fn),global:{}};
  vm.runInNewContext(source,context);
  if(options.manual) await context.global.__darlingLeagueRepairNow();
  else {
    const details={statusCode:options.status || 204,url:'https://127.0.0.1:12345'+(options.path || '/patch-proxy/v2/priority-patch/products/league_of_legends/patchlines/live')};
    callback(details); callback(details);
  }
  for(let n=0;n<1000 && (context.global.__darlingLeagueUpdate.pending || context.global.__darlingLeagueUpdate.rootPending);n++) await new Promise(setImmediate);
  assert.equal(context.global.__darlingLeagueUpdate.pending,false);
  return {writes,sieveRequests,state:context.global.__darlingLeagueUpdate};
}
(async()=> {
  const success=await scenario();
  assert.equal(success.writes.length,1); assert.equal(success.state.submitted,1);
  assert.equal(success.writes[0].body.delete_foreign_paths,false);
  assert.deepEqual(success.writes[0].body.headers,{});
  const both=await scenario({game:'not_installed',stale:true});
  assert.equal(both.writes.filter(w=>w.path.includes('/requests/patch')).length,2);
  assert.equal(both.writes.at(-1).body.updateRequired,false);
  const game=await scenario({client:'up_to_date',game:'not_installed',manual:true});
  assert.equal(game.writes.length,1); assert.ok(game.writes[0].path.includes('game_patch'));
  assert.deepEqual(game.writes[0].body.tags,['en_GB']);
  for(const options of [{active:'client'},{client:'updating'},{client:'up_to_date'},
    {url:'https://example.org/manifest'},{cookies:['protected']},{status:400},{path:'/unrelated'}]) {
    assert.equal((await scenario(options)).writes.length,0);
  }
  const unfinished=await scenario({unfinished:true,stale:true});
  assert.equal(unfinished.writes.length,1);
  assert.equal(unfinished.state.convergence,'unfinished');
  const busy=await scenario({client:'up_to_date',game:'up_to_date',active:'game',stale:true,manual:true});
  assert.equal(busy.writes.length,0);
  const ready=await scenario({client:'up_to_date',game:'up_to_date',stale:true,manual:true});
  assert.equal(ready.writes.length,1);assert.ok(ready.writes[0].path.includes('/app-update/'));
  const rebound=await scenario({client:'up_to_date',game:'out_of_date',legacyRoot:true,nativeGame:true});
  assert.equal(rebound.writes.length,2);
  assert.equal(rebound.writes[0].body.path,'/Applications/League of Legends.app/Contents/LoL/Game');
  assert.equal(rebound.writes[0].body.metadata_path,'/fixture/game');
  assert.deepEqual(rebound.writes[0].body.excluded_paths,['keep']);
  const noGame=await scenario({client:'up_to_date',game:'out_of_date',legacyRoot:true});
  assert.equal(noGame.writes.length,1);
  const activeRoot=await scenario({client:'up_to_date',game:'out_of_date',legacyRoot:true,nativeGame:true,active:'game'});
  assert.equal(activeRoot.writes.length,0);
  const startupRoot=await scenario({client:'up_to_date',game:'up_to_date',legacyRoot:true,nativeGame:true,path:'/unrelated'});
  assert.equal(startupRoot.writes.length,1);
  assert.equal(startupRoot.writes[0].body.path,'/Applications/League of Legends.app/Contents/LoL/Game');
  assert.equal(startupRoot.state.submitted,0);
  const retained=await scenario({retainRequest:true,stale:true});
  assert.equal(retained.state.convergence,'ready');
  assert.equal(retained.writes.filter(w=>w.method==='DELETE').length,1);
  assert.ok(retained.writes.at(-1).path.includes('/app-update/'));
  // The game is repaired to the live Patchsieve release, never the older one in the local config
  const live=await scenario({client:'up_to_date',game:'not_installed',manual:true});
  assert.equal(live.writes[0].body.url,'https://lol.secure.dyn.riotcdn.net/channels/public/releases/66B91DB25E5AD56E.manifest');
  assert.ok(live.sieveRequests[0].includes('/version-sets/EUW1?') && live.sieveRequests[0].includes('platform%5D=macos') === false);
  assert.ok(live.sieveRequests[0].includes('q[platform]=macos'));
  const recorded=await scenario({client:'up_to_date',game:'not_installed',manual:true,recordedUrl:'https://lol.secure.dyn.riotcdn.net/channels/public/releases/BAA127646F53294E.manifest'});
  assert.equal(recorded.writes[0].body.url,'https://lol.secure.dyn.riotcdn.net/channels/public/releases/66B91DB25E5AD56E.manifest');
  // No live release available: do nothing instead of falling back to the stale config
  const down=await scenario({client:'up_to_date',game:'not_installed',manual:true,sieveDown:true});
  assert.equal(down.writes.length,0); assert.equal(down.state.failed,1);
  const unknownRegion=await scenario({client:'up_to_date',game:'not_installed',manual:true,region:'MARS'});
  assert.equal(unknownRegion.writes.length,0); assert.equal(unknownRegion.state.failed,1);
  // Recorded up to date at an older release: converge to the live one; at the live one: no write
  const behind=await scenario({client:'up_to_date',game:'up_to_date',manual:true,recordedUrl:'https://lol.secure.dyn.riotcdn.net/channels/public/releases/BAA127646F53294E.manifest'});
  assert.equal(behind.writes.filter(w=>w.path.includes('game_patch/requests/patch')).length,1);
  assert.equal(behind.writes[0].body.url,'https://lol.secure.dyn.riotcdn.net/channels/public/releases/66B91DB25E5AD56E.manifest');
  const current=await scenario({client:'up_to_date',game:'up_to_date',manual:true,recordedUrl:'https://lol.secure.dyn.riotcdn.net/channels/public/releases/66B91DB25E5AD56E.manifest'});
  assert.equal(current.writes.length,0);
  const installConflict=await scenario({status:409,client:'not_installed',game:'not_installed'});
  assert.equal(installConflict.writes.filter(w=>w.path.includes('/requests/patch')).length,2);
  const interrupted=await scenario({client:'pending_verify',manual:true});
  assert.equal(interrupted.writes.length,1);assert.equal(interrupted.state.convergence,'ready');
  assert.equal((await scenario({status:409,active:'client'})).writes.length,0);
  assert.equal((await scenario({status:409,path:'/unrelated'})).writes.length,0);
  console.log('LEAGUE_UPDATE_HANDOFF cases=28 pass=1');
})().catch(error=>{console.error(error);process.exitCode=1;});
