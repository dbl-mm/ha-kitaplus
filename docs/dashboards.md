# Dashboard-Vorlagen

Die Vorlagen und die Anleitung zum Einbau stehen unter [`dashboards/`](../dashboards/README.md). Hier die Gestaltungsregeln,
nach denen sie gebaut sind, damit Änderungen im selben Sinn bleiben.

1. **Zuerst die Frage, ob etwas zu tun ist.** Status oben, danach nur, was Aufmerksamkeit braucht (bedingte Karten), erst dann
   Einzelheiten. Ist alles erledigt, bleibt der Bereich ruhig.
2. **Einfach statt minimal.** Häufiges steht auf der ersten Ansicht, Seltenes (Kalender, Mitteilungen, Diagnose) eine Ebene
   tiefer. Beschriftungen nennen den Inhalt („Essen morgen“), nicht eine Kategorie.
3. **Farbe trägt nie allein eine Aussage.** Jede Kachel schreibt den Zustand in Worten und hat ein Symbol. Nur Theme-Farben
   (`orange` für „beachten“, `red` für „jetzt handeln“), damit hell und dunkel stimmen.
4. **Ein Diagramm nur, wo es etwas sagt.** Der Kontostand ist eine einzelne Linie ohne Legende, der Titel nennt den Inhalt
   und den Zeitraum.
5. **Nur eingebaute Karten.** Nichts muss nachinstalliert werden und nichts bricht, wenn ein Zusatzpaket nicht mehr gepflegt wird.
6. **Eine Quelle.** `scripts/build_dashboards.py` erzeugt deutsche und englische Fassung sowie die Einzelkarten, damit sie
   nicht auseinanderlaufen. `tests/test_dashboards.py` prüft die Regeln oben und dass jede Entity-ID existiert.
