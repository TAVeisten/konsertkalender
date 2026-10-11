#!/usr/bin/env python3
"""Build the GitHub Pages version (index.html) from the Claude artifact HTML.

The artifact at claude.ai is the master copy (the daily update edits it).
This script copies it and adds what only works outside claude.ai:
  - "Finn min posisjon" (the phone's GPS)
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

# GPS button in the "Nær meg" panel
rep('  const go=el("button","ppgo","Bruk"); go.type="button"; row.append(inp,go);',
    '  const go=el("button","ppgo","Bruk"); go.type="button"; row.append(inp,go);\n'
    '  const gpsB=el("button","ppbtn ppmain","📍 Finn min posisjon"); gpsB.type="button";')
rep('box.append(meOpt,webHint,lab,row,cands,cur,err);', 'box.append(meOpt,gpsB,lab,row,cands,cur,err);')
rep('  window.__showCur=showCur; showCur();',
    '''  window.__showCur=showCur; showCur();
  const getGps=manual=>{ if(!navigator.geolocation){ if(manual) err.textContent="Denne nettleseren kan ikke gi posisjon. Skriv adresse i stedet."; return; }
    if(manual) err.textContent="Finner posisjonen din …";
    navigator.geolocation.getCurrentPosition(p=>{ const v=[Math.round(p.coords.latitude*1e5)/1e5,Math.round(p.coords.longitude*1e5)/1e5];
        if(!manual&&!(state.home==="__me")) return;
        setLoc(v,"Min posisjon",false,false); store("kk-megps",true); savePrefs();
        geoRev(v).then(g=>{ if(g&&meLoc&&meLoc[0]===v[0]&&meLoc[1]===v[1]){ meLabel="Min posisjon – nær "+g; store("kk-melabel",meLabel); savePrefs(); showCur(); syncHome(); } }); },
      e=>{ if(manual) err.textContent = e&&e.code===1 ? "Posisjon er ikke tillatt for denne siden. Slå det på i telefonens innstillinger for nettleseren, eller skriv adresse." : "Fant ikke posisjonen din. Prøv igjen, eller skriv adresse."; },
      {enableHighAccuracy:true,timeout:15000,maximumAge:120000}); };
  gpsB.addEventListener("click",ev=>{ ev.stopPropagation(); getGps(true); });
  if(load("kk-megps",false) && state.home==="__me") setTimeout(()=>getGps(false),300);''')
# street search: fetch many pages (only street + municipality fields) so all matching streets show up
rep('      let rows=await geoRaw("sok="+encodeURIComponent(t.trim()+"*")+"&treffPerSide=500");',
    r'''      const tl=t.trim().toLowerCase(), hit=x=>{ const n=(x.street||"").toLowerCase(); return n.startsWith(tl)||n.split(/[\s-]+/).some(w=>w.startsWith(tl)); };
      let rows=await streetsAll("adressenavn",t.trim()+"*"); if(!rows||!rows.some(hit)) rows=await streetsAll("sok",t.trim()+"*"); if(!rows) rows=await geoRaw("sok="+encodeURIComponent(t.trim()+"*")+"&treffPerSide=500");
      if(rows&&rows.some(hit)){ const tot=rows.total; rows=rows.filter(hit); rows.total=tot; }''')
rep('  const geo=async q=>{',
    """  const streetsAll=async(fld,q)=>{ const F="&filtrer=adresser.adressenavn,adresser.kommunenavn,adresser.representasjonspunkt,metadata&utkoordsys=4258";
      const pg=async n=>{ try{ const c=new AbortController(); const tm=setTimeout(()=>c.abort(),10000);
        const r=await fetch("https://ws.geonorge.no/adresser/v1/sok?"+fld+"="+encodeURIComponent(q)+"&treffPerSide=1000&side="+n+F,{signal:c.signal}); clearTimeout(tm);
        if(!r.ok) return null; const j=await r.json(); return Array.isArray(j.adresser)?j:null; }catch(e){ return null; } };
      const first=await pg(0); if(!first) return null; let all=first.adresser;
      let total=(first.metadata&&first.metadata.totaltAntallTreff)||(all.length>=1000?10000:all.length);
      const n=Math.min(Math.ceil(total/1000),10); if(n>1){ const more=await Promise.all(Array.from({length:n-1},(_,i)=>pg(i+1))); more.forEach(m=>{ if(m) all=all.concat(m.adresser); }); }
      const out=all.map(x=>({street:x.adressenavn||"",kom:cap(x.kommunenavn),la:x.representasjonspunkt&&x.representasjonspunkt.lat,lo:x.representasjonspunkt&&x.representasjonspunkt.lon})); out.total=total; return out; };
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
        streets.sort((a,b)=>a._t-b._t||a.street.localeCompare(b.street,"nb")||a._d-b._d||a.kom.localeCompare(b.kom,"nb"));""")
rep('        streets.forEach(x=>{ const bt=el("button","popt pcity");',
    '        let hOther=false; streets.forEach(x=>{ if(x._t>=3&&!hOther&&streets[0]._t<3){ hOther=true; cands.append(el("p","pplab","Andre gater med «"+t.trim()+"»")); } const bt=el("button","popt pcity");')
# GPS label: keep the home button short
rep('(meLabel&&!parseLoc(meLabel)?meLabel.split(",")[0]:"Min posisjon")', '(meLabel&&!parseLoc(meLabel)&&!meLabel.startsWith("Min posisjon")?meLabel.split(",")[0]:"Min posisjon")')
# typing an address or coordinates turns automatic GPS off
rep('  const use=async(ta)=>{ ta=ta===true; const t=inp.value.trim(); if(!t||busy) return;',
    '  const use=async(ta)=>{ ta=ta===true; const t=inp.value.trim(); if(!t||busy) return; if(!ta) store("kk-megps",false);')
rep('"Min adresse eller posisjon"', '"Eller skriv adresse"')
rep('Avstand regnes i luftlinje fra posisjonen du har limt inn,', 'Avstand regnes i luftlinje fra posisjonen din eller adressen du har skrevet inn,')

open(dst, "w", encoding="utf-8").write(s)
print("build_site: wrote", dst, len(s), "bytes")
