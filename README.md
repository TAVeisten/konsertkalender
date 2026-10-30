# Konsertkalender Norge

Kommende konserter i Norge, med hovedvekt på Oslo- og Drammensområdet, Bergen og Trondheim.

- `index.html` er selve appen (GitHub Pages).
- `artifact.html` er en kopi av Claude-artefakten slik den ble publisert sist (med alle data).
- `tools/build_site.py` lager `index.html` fra artefakten og legger til «Min posisjon» og adressesøk mot Kartverket.
- `tools/update.py` gjør det faste arbeidet i den daglige oppdateringen: leser dataene i siden, fletter inn nye
  konserter og festivaler, fjerner dubletter og passerte konserter, holder orden på spillestedenes posisjoner,
  lager sammendraget og tidsstempelet og sjekker at skriptene i siden er gyldige. Se toppen av filen for bruk.
- `favoritter.json` er stjernene, favorittartistene og favorittstedene. Siden skriver den selv (med en GitHub-nøkkel
  som limes inn én gang under Innstillinger i hvert sted siden åpnes – Safari og Mine sider teller hver for seg),
  så de er like overalt der nøkkelen er lagt inn. Den daglige oppdateringen
  leser den og lager seksjonen «Nytt fra favorittene» øverst i sammendraget.
- Konsertlisten oppdateres automatisk hver dag.
