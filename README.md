# TextRescue

Merkt sich, was du tippst, und holt verlorenen Text zurück – etwa wenn du ein
Fenster versehentlich schließt. Bedient wird es über ein **Symbol rechts unten
bei der Uhr** (Taskleiste). Rechtsklick auf das Symbol:

- **Öffnen** – zeigt den gemerkten Text, Knopf „Alles kopieren“, Löschen (mit Haken)
- **Zeitgesteuertes Löschen pausieren** – automatisches Löschen aus; die
  Pfeilspitze im Icon wird dann **rot**, der Menüeintrag zeigt ein Pausezeichen
- **Optionen** – alle Einstellungen
- **Info** – Erklärung direkt im Programm
- **Beenden**

## So funktioniert es

- Der getippte Text lebt standardmäßig **nur im Arbeitsspeicher** und wird
  **nicht auf die Festplatte geschrieben**.
- Der Puffer löscht sich selbst: nach einer eingestellten Zahl von Zeichen
  (mit A4-Schätzung) oder nach einer eingestellten Zeit der Untätigkeit.
- **Mausbewegung als Aktivität (Option):** zählt Mausbewegung als Aktivität und
  zögert so das automatische Löschen hinaus.
- Umlaute, ß und AltGr-Zeichen (@, €) sowie Groß-/Kleinschreibung werden korrekt
  erfasst.
- Anwendungswechsel (z. B. Word → Chrome) erzeugt eine Trennzeile im Mitschnitt.
- Passwortfelder werden nicht mitgeschrieben (wenn `uiautomation` installiert
  ist). Diese Erkennung ist nicht zu 100 % garantiert.
- **Nur eine Instanz** läuft gleichzeitig.
- Oberfläche **Deutsch/Englisch** (Umschalten in den Optionen, mit Flaggen).

## Optionen

- **Automatisch mit Windows starten** – trägt TextRescue in den Windows-Autostart
  ein bzw. wieder aus.
- **Absturzsicher** (standardmäßig aus) – der Text wird in `buffer.dat` im
  TextRescue-Ordner gespeichert und übersteht so einen Neustart (z. B.
  Stromausfall). **Risiko:** Der Text liegt dann unverschlüsselt auf der
  Festplatte und kann, selbst nach dem Löschen, durch Experten möglicherweise
  wiederhergestellt werden. Beim Ausschalten und bei „Jetzt löschen“ wird
  `buffer.dat` gelöscht.
- **Geheimagenten-Modus** – blendet das Icon in der Taskleiste aus. TextRescue
  ist dann nicht mehr sichtbar oder steuerbar, auch nach einem Neustart nicht.
  Zurück nur durch erzwungenes Beenden über den Task-Manager (Speicher wird
  dabei gelöscht, sofern nicht „Absturzsicher“ aktiv ist) und Neustart, **oder**
  durch Tippen der Tastenfolge `#rescue#`.

## Die exe bauen

Du brauchst einmalig **Python** (python.org, beim Setup „Add to PATH“ anhaken).
Dann:

1. Alle Dateien in **einen** Ordner legen.
2. Doppelklick auf **`build.bat`**.
3. Die fertige Datei liegt danach in `dist\TextRescue.exe`.

`build.bat` baut nur – gestartet wird nicht automatisch. Starten per Doppelklick
auf `TextRescue.exe`; das Symbol erscheint unten rechts bei der Uhr.

Autostart lässt sich auch direkt in den Optionen aktivieren.

## Dateien im Projekt

```
textrescue/
├─ textrescue.py       # das Programm
├─ build.bat           # exe bauen (Windows, Doppelklick)
├─ requirements.txt    # Python-Pakete
├─ README.md           # diese Datei
├─ .gitignore          # hält buffer.dat / config.json / dist aus GitHub heraus
├─ icon.ico            # Datei-Icon der exe (16/32/48/256)
├─ icon.png            # Tray-Symbol normal (grüner Pfeil)
├─ icon_paused.png     # Tray-Symbol bei Pause (roter Pfeil)
├─ flag_de.png         # Flagge für Sprachwahl (Deutsch)
├─ flag_en.png         # Flagge für Sprachwahl (Englisch)
└─ lorem10000.txt      # Beispieltext, 10.000 Zeichen
```

**Wichtig:** `icon.png`, `icon_paused.png`, `flag_de.png` und `flag_en.png`
müssen beim Bauen im selben Ordner wie `textrescue.py` liegen. `build.bat` bindet
sie in die exe ein.

## Virenscanner

Ein Programm, das alles Getippte mitliest, ist technisch dasselbe wie ein
Keylogger. **Windows Defender oder andere Virenscanner können die exe
blockieren oder in Quarantäne verschieben.** Das ist kein Fehler – du musst das
Programm dann selbst als Ausnahme erlauben. Wenn du die exe weitergibst, werden
fremde Scanner dasselbe tun.
