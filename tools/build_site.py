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
rep('box.append(meOpt,lab,row,cands,cur,err);', 'box.append(meOpt,gpsB,lab,row,cands,cur,err);')
rep('  window.__showCur=showCur; showCur();',
    '''  window.__showCur=showCur; showCur();
  const getGps=manual=>{ if(!navigator.geolocation){ if(manual) err.textContent="Denne nettleseren kan ikke gi posisjon. Skriv adresse i stedet."; return; }
    if(manual) err.textContent="Finner posisjonen din …";
    navigator.geolocation.getCurrentPosition(p=>{ const v=[Math.round(p.coords.latitude*1e5)/1e5,Math.round(p.coords.longitude*1e5)/1e5];
        if(!manual&&!(state.home==="__me")) return;
        setLoc(v,"Min posisjon",false,false); store("kk-megps",true); savePrefs(); },
      e=>{ if(manual) err.textContent = e&&e.code===1 ? "Posisjon er ikke tillatt for denne siden. Slå det på i telefonens innstillinger for nettleseren, eller skriv adresse." : "Fant ikke posisjonen din. Prøv igjen, eller skriv adresse."; },
      {enableHighAccuracy:true,timeout:15000,maximumAge:120000}); };
  gpsB.addEventListener("click",ev=>{ ev.stopPropagation(); getGps(true); });
  if(load("kk-megps",false) && state.home==="__me") setTimeout(()=>getGps(false),300);''')
# typing an address or coordinates turns automatic GPS off
rep('  const use=async(ta)=>{ ta=ta===true; const t=inp.value.trim(); if(!t||busy) return;',
    '  const use=async(ta)=>{ ta=ta===true; const t=inp.value.trim(); if(!t||busy) return; if(!ta) store("kk-megps",false);')
rep('"Min adresse eller posisjon"', '"Eller skriv adresse"')
rep('Avstand regnes i luftlinje fra posisjonen du har limt inn,', 'Avstand regnes i luftlinje fra posisjonen din eller adressen du har skrevet inn,')

open(dst, "w", encoding="utf-8").write(s)
print("build_site: wrote", dst, len(s), "bytes")
