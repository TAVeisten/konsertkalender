# Konsertkalender Norge

Kommende konserter i Norge, med hovedvekt på Oslo-området, Bergen, Trondheim og Drammen.

- `index.html` er selve appen (GitHub Pages).
- `artifact.html` er en kopi av Claude-artefakten slik den ble publisert sist (med alle data).
- `tools/build_site.py` lager `index.html` fra artefakten og legger til «Min posisjon» og adressesøk mot Kartverket.
- `tools/update.py` gjør det faste arbeidet i den daglige oppdateringen: leser dataene i siden, fletter inn nye
  konserter og festivaler, fjerner dubletter og passerte konserter, holder orden på spillestedenes posisjoner,
  lager sammendraget og tidsstempelet og sjekker at skriptene i siden er gyldige. Se toppen av filen for bruk.
- Konsertlisten oppdateres automatisk hver dag.
