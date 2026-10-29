# Dashboard-Vorlagen

Die Vorlagen und die Anleitung zum Einbau stehen unter [`dashboards/`](../dashboards/README.md). Hier die Gestaltungsregeln,
nach denen sie gebaut sind, damit Änderungen im selben Sinn bleiben.

1. **So wenig wie möglich.** Jede Information steht einmal da. Was fehlt, fehlt mit Absicht: kein Diagramm mit einem einzigen
   Punkt, keine Diagnose-Ansicht, kein zweiter Kalender, keine Wiederholung von Überschrift, Kachel und Titel.
2. **Handlung zuerst, und nur wenn nötig.** Ein Bereich ohne Überschrift ganz oben enthält nur bedingte Karten. Gibt es nichts zu
   tun, sind alle ausgeblendet und der Bereich verschwindet. Es steht dort nie „alles in Ordnung“ als Füllmaterial.
3. **Niemand wird zu etwas Unmöglichem aufgefordert.** Eine Aufforderung zum Bestellen erscheint nur beim Status „Offen“, nie bei
   „Frist verpasst“.
4. **Farbe trägt nie allein eine Aussage.** Jede Kachel schreibt den Zustand in Worten und hat ein Symbol. Nur Theme-Farben
   (`orange` für „beachten“, `red` für „jetzt handeln“), damit hell und dunkel stimmen.
5. **Eine Zeile pro Fakt.** „Bestellt · Mittagessen“ statt zwei Kacheln. Kurze Namen („Heute“, „Morgen“), weil die Überschrift schon
   sagt, um wen es geht.
6. **Listen sind Auszüge.** Titel, Datum und ein kurzer Textanfang. Formatierungszeichen, die Kitas in Titel schreiben, werden
   entfernt, damit nie lose Sternchen erscheinen.
7. **Nur eingebaute Karten.** Nichts muss nachinstalliert werden, und nichts bricht, wenn ein Zusatzpaket nicht mehr gepflegt wird.
8. **Eine Quelle.** `scripts/build_dashboards.py` erzeugt die deutsche und die englische Fassung sowie die Einzelkarten.
   `tests/test_dashboards.py` prüft die Regeln oben und dass jede Entity-ID existiert.
