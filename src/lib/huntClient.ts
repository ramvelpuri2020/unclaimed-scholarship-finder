'use client';
import { createPrograms, sites } from './mockPrograms';
import { useStore } from './store';
import type { Profile, Program } from './types';
const wait=(ms:number)=>new Promise<void>(resolve=>window.setTimeout(resolve,ms));
export async function startHunt(_profile:Profile): Promise<string> {
  const id='demo'; const store=useStore.getState(); store.start(id,sites.map(s=>s.id),Object.fromEntries(sites.map(s=>[s.id,s.name])));
  const programs=createPrograms();
  for(let i=0;i<sites.length;i++){
    const site=sites[i]; await wait(i===0?0:1400); store.event({type:'site_started',siteId:site.id,siteName:site.name});
    if(site.id==='provincial'){
      await wait(4000); store.event({type:'site_failed',siteId:site.id,usedCache:true});
      const matches=programs.filter(p=>p.sourceSiteId===site.id);
      for(const program of matches){await wait(500);store.event({type:'program_found',program});}
      store.event({type:'site_done',siteId:site.id,count:matches.length}); continue;
    }
    for(const [delay,message] of [[1200,`Opening ${site.name}`],[1400,'Reading eligibility details'],[1400,'Checking against your answers']] as const){await wait(delay);store.event({type:'site_progress',siteId:site.id,message});}
    await wait(600);
    const matches=programs.filter(p=>p.sourceSiteId===site.id);
    for(const program of matches){await wait(500);store.event({type:'program_found',program});}
    store.event({type:'site_done',siteId:site.id,count:matches.length});
  }
  const state=useStore.getState(); state.event({type:'hunt_complete',totalAmount:state.total,programCount:state.programs.length}); return id;
}
export type ProgramResult = Program[];
