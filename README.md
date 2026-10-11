# Konsertkalender Norge

Kommende konserter i Norge, med hovedvekt på Oslo-området, Bergen, Trondheim og Drammen.

- `index.html` er selve appen (GitHub Pages).
- Den lages fra Claude-artefakten med `python3 tools/build_site.py <artefakt.html> index.html`,
  som legger til «Finn min posisjon» og adressesøk mot Kartverket.
- Konsertlisten oppdateres automatisk hver dag.
