#!/usr/bin/env python3
"""Build the GitHub Pages version (index.html) from the Claude artifact HTML.

The artifact at claude.ai is the master copy (the daily update edits it).
This script copies it and adds what only works outside claude.ai:
  - "Min posisjon" (the phone's GPS) as its own choice next to "Hjem" (the typed address)
  - address search that goes straight to Kartverket (already in the code; works here)

Usage: python3 tools/build_site.py <artifact.html> <index.html>
"""
import sys, re

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()

def rep(old, new, count=1):
    global s
    if s.count(old) != count:
        sys.exit(f"build_site: expected {count} x {old[:70]!r}, found {s.count(old)}")
    s = s.replace(old, new)

# Page head: language, phone home-screen settings
rep('<!doctype html><html><head>', '<!doctype html><html lang="no"><head>')
rep('<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">',
    '<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="theme-color" content="#D23347"><meta name="apple-mobile-web-app-capable" content="yes">'
    '<meta name="apple-mobile-web-app-title" content="Konserter"><meta name="mobile-web-app-capable" content="yes">')



# --- Hjem + Min posisjon as two separate places ---
# meLoc/meLabel = Hjem (typed address, home value "__me"); gpsLoc/gpsLabel = Min posisjon (phone GPS, home value "__gps")
rep('let meLoc=load("kk-meloc",null), meLabel=load("kk-melabel",""), meApprox=load("kk-meapprox",false);',
    r'''let meLoc=load("kk-meloc",null), meLabel=load("kk-melabel",""), meApprox=load("kk-meapprox",false);
let gpsLoc=load("kk-gpsloc",null), gpsLabel=load("kk-gpslabel","");
if(meLoc&&String(meLabel).startsWith("Min posisjon")){ gpsLoc=meLoc; store("kk-gpsloc",gpsLoc); gpsLabel=String(meLabel).replace(/^Min posisjon( – nær )?/,""); store("kk-gpslabel",gpsLabel);
  meLoc=null; store("kk-meloc",null); meLabel=""; store("kk-melabel",""); if(state.home==="__me"){ state.home="__gps"; store("kk-home","__gps"); } }''')
rep('const homePos=()=>state.home==="__me"?meLoc:(HOMES[state.home]||null);',
    'const homePos=()=>state.home==="__me"?meLoc:state.home==="__gps"?gpsLoc:(HOMES[state.home]||null);')
rep('fill($("home"), ["__me"].concat(', 'fill($("home"), ["__me","__gps"].concat(')
rep('homeBtn.textContent=state.home==="__me"&&meLoc?"📍 "+(meLabel&&!parseLoc(meLabel)?meLabel.split(",")[0]:"Min posisjon"):',
    'homeBtn.textContent=state.home==="__gps"&&gpsLoc?"📍 Min posisjon":state.home==="__me"&&meLoc?"🏠 Hjem":')
rep('$("home").value = (HOMES[state.home]||(state.home==="__me"&&meLoc)) ? state.home : "";',
    '$("home").value = (HOMES[state.home]||(state.home==="__me"&&meLoc)||(state.home==="__gps"&&gpsLoc)) ? state.home : "";')
rep('if(state.home==="__me"&&!meLoc){ state.home=""; $("home").value=""; }',
    'if((state.home==="__me"&&!meLoc)||(state.home==="__gps"&&!gpsLoc)){ state.home=""; $("home").value=""; }')
rep('  const go=el("button","ppgo","Bruk"); go.type="button"; row.append(inp,go);',
    '  const go=el("button","ppgo","Bruk"); go.type="button"; row.append(inp,go);\n'
    '  const gpsOpt=el("button","popt"); gpsOpt.type="button"; gpsOpt.dataset.home="__gps"; gpsOpt.append(el("span",null,"📍 Min posisjon"));')
rep('box.append(meOpt,webHint,lab,row,cands,cur,err);', 'box.append(gpsOpt,meOpt,lab,row,cands,cur,err);')
rep('''  const showCur=()=>{ const inUse=state.home==="__me"&&meLoc; meOpt.hidden=!meLoc||inUse;
    cur.textContent = meLoc ? (inUse?"✓ I bruk: ":"Lagret: ")+(meLabel?meLabel+" ("+fmtC(meLoc)+")":fmtC(meLoc))+(meApprox?" – omtrentlig, sjekk avstandene":"") : ""; };''',
    '''  const showCur=()=>{ meOpt.hidden=!meLoc; if(meLoc) meOpt.firstChild.textContent="🏠 Hjem – "+(meLabel&&!parseLoc(meLabel)?meLabel.split(",")[0]:fmtC(meLoc));
    lab.textContent=meLoc?"Endre hjemadresse":"Sett hjemadresse";
    cur.textContent = state.home==="__gps"&&gpsLoc ? "✓ I bruk: Min posisjon"+(gpsLabel?" – nær "+gpsLabel:"")+" ("+fmtC(gpsLoc)+")"
      : meLoc ? (state.home==="__me"?"✓ I bruk: Hjem – ":"Hjem: ")+(meLabel?meLabel+" ("+fmtC(meLoc)+")":fmtC(meLoc))+(meApprox?" – omtrentlig, sjekk avstandene":"") : ""; };''')
rep('  window.__showCur=showCur; showCur();',
    """  window.__showCur=showCur; showCur();
  const useGps=()=>{ const sel=$("home"); sel.value="__gps"; sel.dispatchEvent(new Event("change")); showCur(); syncHome(); };
  const getGps=manual=>{ if(!navigator.geolocation){ if(manual) err.textContent="Denne nettleseren kan ikke gi posisjon."; return; }
    if(manual) err.textContent="Finner posisjonen din …";
    navigator.geolocation.getCurrentPosition(p=>{ const v=[Math.round(p.coords.latitude*1e5)/1e5,Math.round(p.coords.longitude*1e5)/1e5];
        if(!manual&&state.home!=="__gps") return;
        gpsLoc=v; store("kk-gpsloc",v); err.textContent=""; useGps(); if(manual) closeP();
        geoRev(v).then(g=>{ if(g&&gpsLoc===v){ gpsLabel=g; store("kk-gpslabel",g); showCur(); } }); },
      e=>{ if(manual) err.textContent = e&&e.code===1 ? "Posisjon er ikke tillatt for denne siden. Slå det på i telefonens innstillinger for nettleseren, eller bruk Hjem." : "Fant ikke posisjonen din. Prøv igjen, eller bruk Hjem."; },
      {enableHighAccuracy:true,timeout:15000,maximumAge:60000}); };
  gpsOpt.addEventListener("click",ev=>{ ev.stopPropagation(); if(gpsLoc){ useGps(); closeP(); getGps(false); } else getGps(true); });
  if(state.home==="__gps") setTimeout(()=>getGps(false),300);""")
# street search: fetch many pages (only street + municipality fields) so all matching streets show up
rep('      let rows=await geoRaw("sok="+encodeURIComponent(t.trim()+"*")+"&treffPerSide=500");',
    r'''      const tl=t.trim().toLowerCase(), hit=x=>{ const n=(x.street||"").toLowerCase(); return n.startsWith(tl)||n.split(/[\s-]+/).some(w=>w.startsWith(tl)); };
      let rows=await streetsAll("adressenavn",t.trim()+"*"); if(!rows||!rows.some(hit)) rows=await streetsAll("sok",t.trim()+"*"); if(!rows) rows=await geoRaw("sok="+encodeURIComponent(t.trim()+"*")+"&treffPerSide=500");
      if(rows&&rows.some(hit)){ const more=rows.total>rows.length; rows=rows.filter(hit); rows.total=rows.length+(more?1:0); }''')
rep('  const geo=async q=>{',
    r"""  const streetsAll=async(fld,q)=>{ const F="&filtrer=adresser.adressenavn,adresser.kommunenavn,adresser.representasjonspunkt,metadata&utkoordsys=4258";
      const pg=async(qq,n)=>{ try{ const c=new AbortController(); const tm=setTimeout(()=>c.abort(),12000);
        const r=await fetch("https://ws.geonorge.no/adresser/v1/sok?"+fld+"="+encodeURIComponent(qq)+"&treffPerSide=1000&side="+n+F,{signal:c.signal}); clearTimeout(tm);
        if(!r.ok) return null; const j=await r.json(); return Array.isArray(j.adresser)?j:null; }catch(e){ return null; } };
      let cut=false;
      const one=async(qq,split)=>{ const first=await pg(qq,0); if(!first) return null; let all=first.adresser;
        const total=(first.metadata&&first.metadata.totaltAntallTreff)||(all.length>=1000?10000:all.length);
        if(total>=10000&&split){ // too many to fetch: the API returns them alphabetically and stops at 10000, so ask once per next letter
          const base=qq.replace(/\*$/,""), L="abcdefghijklmnopqrstuvwxyzæøå".split(""), subs=L.map(c=>base+c+"*").concat(/\s$/.test(base)?[]:L.map(c=>base+" "+c+"*"));
          const parts=await Promise.all(subs.map(x=>one(x,false))); all=[]; parts.forEach(p=>{ if(p) all=all.concat(p); }); return all; }
        if(total>=10000) return all; // a letter query that still matches too much (e.g. "Øvre ø*" also hits "Øvre"): first page is enough
        const n=Math.min(Math.ceil(total/1000),10); if(n>1){ const more=await Promise.all(Array.from({length:n-1},(_,i)=>pg(qq,i+1))); more.forEach(m=>{ if(m) all=all.concat(m.adresser); }); }
        return all; };
      const all=await one(q,true); if(!all) return null;
      const out=all.map(x=>({street:x.adressenavn||"",kom:cap(x.kommunenavn),la:x.representasjonspunkt&&x.representasjonspunkt.lat,lo:x.representasjonspunkt&&x.representasjonspunkt.lon})); out.total=cut?out.length+1:out.length; return out; };
  const geo=async q=>{""")
# after showing a new list, scroll the panel so the list starts at the top (not left down in the city list)
rep('            err.textContent=""; cands.append(el("p","pplab","Velg husnummer i "+x.street+", "+x.kom));',
    '            err.textContent=""; cands.append(el("p","pplab","Velg husnummer i "+x.street+", "+x.kom)); homePanel.scrollTop+=cands.getBoundingClientRect().top-homePanel.getBoundingClientRect().top-8;')
# street list ordering: whole word first, then compounds, then later words; same name sorted by distance
rep('        streets.sort((a,b)=>(a.street+a.kom).localeCompare(b.street+b.kom,"nb"));',
    r"""        const tq=t.trim().toLowerCase(), SUF=/(veien|vegen|veg|vei|gata|gaten|gate|bakken|bakke|stien|sti|svingen|lia|plassen|plass|alle|allé|tunet|toppen|haugen|åsen|kroken|brinken|stredet|smauet|grenda|jordet|ringen|kollen|lunden|myra|enga|engen|løkka|kaia|kaien|brygga|bryggen|torget|torg|veita|stranda|strand|parken|park|hagen|dalen|berget|vika|tråkket|marka|lykkja|svea)$/;
        const tier=n=>{ n=n.toLowerCase(); let best=9; for(let i=n.indexOf(tq);i>=0;i=n.indexOf(tq,i+1)){ if(i>0&&!/[\s.-]/.test(n[i-1])) continue;
            const rest=n.slice(i+tq.length), whole=!rest||/^[\s-]/.test(rest), word=(tq.split(/\s+/).pop()+rest).split(/[\s-]/)[0], comp=!whole&&SUF.test(word)&&word.length>tq.length;
            const v = i===0 ? (whole?0:comp?2:1) : (whole?3:4); if(v<best) best=v; } return best; };
        const hp=homePos(); streets.forEach(x=>{ x._t=tier(x.street); x._d=hp&&okNo(x.la,x.lo)?km(hp,[x.la,x.lo]):1e9; });
        if(streets.some(x=>x._t===0)){ const keep=streets.filter(x=>x._t===0); streets.length=0; streets.push(...keep); } // whole word typed: skip longer names
        streets.sort((a,b)=>a._t-b._t||a.street.localeCompare(b.street,"nb")||a._d-b._d||a.kom.localeCompare(b.kom,"nb"));""")
rep('        streets.forEach(x=>{ const bt=el("button","popt pcity");',
    '        let hOther=false; streets.forEach(x=>{ if(x._t>=3&&!hOther&&streets[0]._t<3){ hOther=true; cands.append(el("p","pplab","Andre gater med «"+t.trim()+"»")); } const bt=el("button","popt pcity");')
# full addresses (also from the phone's autofill): drop county/country words, retry with street + number + postcode
rep('    const g=await geo(t);',
    r"""    const clean=x=>x.replace(/\n/g,", ").replace(/\b(norge|norway|noreg|buskerud|viken|akershus|østfold|vestfold|telemark|agder|rogaland|vestland|hordaland|møre og romsdal|trøndelag|nordland|troms|finnmark|innlandet|oppland|hedmark)\b/gi," ").replace(/\s+/g," ").replace(/[ ,]+$/,"").trim();
    let g=await geo(clean(t)); if(g&&!g.length){ const m=clean(t).match(/^(\D+?\s\d+\s?[a-zA-Z]?)\b.*?\b(\d{4})\b/); if(m) g=await geo(m[1]+" "+m[2]); }""")
rep(r'    if(t.length<3||/\d/.test(t)||parseLoc(t)) return;',
    '    if(/^\\D+\\s\\d+.*\\b\\d{4}\\b/.test(t)&&!parseLoc(t)){ tah=setTimeout(()=>{ if(inp.value.trim()===t) use(); },600); return; }\n    if(t.length<3||/\\d/.test(t)||parseLoc(t)) return;')
rep('"Min adresse eller posisjon"', '"Sett hjemadresse"')
rep('Avstand regnes i luftlinje fra posisjonen du har limt inn,', 'Avstand regnes i luftlinje fra posisjonen din eller adressen du har skrevet inn,')

open(dst, "w", encoding="utf-8").write(s)
print("build_site: wrote", dst, len(s), "bytes")
