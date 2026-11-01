"""
TextRescue - Zwischenspeicher aller getippten Inhalte fuer Windows
==================================================================

Merkt sich systemweit, was du tippst, und laesst dich verlorenen Text
wiederherstellen - z. B. wenn du ein Fenster versehentlich schliesst.

Bedienung über ein Symbol rechts unten bei der Uhr (Tray). Rechtsklick:
  Wiederherstellen / Jetzt löschen (Menü) / Optionen / Info /
  Sprache / Beenden.

- Standard: Text lebt NUR im Arbeitsspeicher, nie auf der Festplatte.
- Option "Absturzsicher": Text verschluesselt auf Platte, bleibt nach Neustart.
- Puffer löscht sich selbst: nach X Zeichen ODER nach Y Minuten Untätigkeit.
- Untätigkeit kann optional auch durch Mausbewegung zurückgesetzt werden.
- "Loeschen pausieren": zeitgesteuertes Loeschen aus, Icon-Pfeil wird rot.
- Passwortfelder werden nicht mitgeschrieben (wenn 'uiautomation' da ist).
- Anwendungswechsel (Word -> Chrome) erzeugt eine Trennzeile im Mitschnitt.
- Keine störenden Popups: Rückmeldungen erscheinen dezent im Fenster.

Abhaengigkeiten (Windows):
    pip install keyboard pystray pillow uiautomation
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import webbrowser
import time
from dataclasses import dataclass, asdict

CHARS_PER_A4 = 3000

# --- Farben / Stil (modern, flach) -----------------------------------------
GREEN = "#1aa333"
RED = "#d23b3b"
BG = "#f4f6f8"          # Fensterhintergrund
CARD = "#ffffff"        # Flaechen
FG = "#1f2430"          # Haupttext
MUTED = "#6b7280"       # Nebentext
ACCENT = "#2d6cdf"
NOTE = "#475569"        # dezenter Hinweistext (statt Braun-Orange)
NOTE_BG = "#eef2f7"     # ruhige Hinterlegung fuer Hinweise


# ---------------------------------------------------------------------------
# Zeichen aus Tastendruck korrekt ermitteln (Umlaute, ß, AltGr @ € ...).
# ---------------------------------------------------------------------------
def char_from_event(event):
    try:
        user32 = ctypes.windll.user32
        scan = getattr(event, "scan_code", None)
        if not scan:
            raise ValueError
        vk = user32.MapVirtualKeyW(scan, 1)        # MAPVK_VSC_TO_VK

        # WICHTIG: In einem globalen Tastatur-Hook ist GetKeyboardState NICHT
        # aktuell - Shift/AltGr etc. fehlen dort. Deshalb den Zustand der
        # Modifier-Tasten in Echtzeit ueber GetAsyncKeyState setzen.
        state = (ctypes.c_ubyte * 256)()
        user32.GetKeyboardState(ctypes.byref(state))
        HIGH = 0x8000
        # generische + linke/rechte Modifier (fuer AltGr = Strg+Alt rechts)
        for mvk in (0x10, 0x11, 0x12,          # SHIFT, CONTROL, MENU(Alt)
                    0xA0, 0xA1,                 # L/R SHIFT
                    0xA2, 0xA3,                 # L/R CONTROL
                    0xA4, 0xA5):                # L/R MENU (AltGr = RMENU)
            state[mvk] = 0x80 if (user32.GetAsyncKeyState(mvk) & HIGH) else 0
        # CapsLock als Umschaltzustand (unterstes Bit)
        state[0x14] = user32.GetKeyState(0x14) & 1

        buf = ctypes.create_unicode_buffer(8)
        hkl = user32.GetKeyboardLayout(0)
        n = user32.ToUnicodeEx(vk, scan, ctypes.byref(state), buf, len(buf), 0, hkl)
        if n > 0 and buf.value and buf.value.isprintable():
            return buf.value
    except Exception:
        pass
    name = getattr(event, "name", None)
    if name and len(name) == 1 and name.isprintable():
        return name
    return None


# --- optionale Pakete -------------------------------------------------------
try:
    import keyboard
    HAVE_KEYBOARD = True
except Exception:
    HAVE_KEYBOARD = False

try:
    import pystray
    from PIL import Image, ImageDraw
    HAVE_TRAY = True
except Exception:
    HAVE_TRAY = False

try:
    import uiautomation as auto
    HAVE_UIA = True
except Exception:
    HAVE_UIA = False


import tkinter as tk
from tkinter import ttk, scrolledtext


# ===========================================================================
# Uebersetzungen
# ===========================================================================
_INFO_DE = """\
TextRescue - Kurzinfo

WAS ES TUT
TextRescue merkt sich, was du tippst, damit du Text zurückholen kannst, wenn ein Fenster abstürzt oder du es versehentlich schließt. Bedienung über das Symbol rechts unten bei der Uhr (Rechtsklick).

SO ARBEITET ES
- Der Text wird standardmäßig NUR im Arbeitsspeicher gehalten und NICHT auf die Festplatte geschrieben.
- Er löscht sich selbst: nach einer eingestellten Zahl von Zeichen oder nach einer eingestellten Zeit der Untätigkeit (Optionen).
- Optional kann auch Mausbewegung als Aktivität zählen und so das automatische Löschen hinauszögern.
- Mit "Löschen pausieren" schaltest du das zeitgesteuerte Löschen ganz ab; die Pfeilspitze im Taskleisten-Icon wird dann rot.
- Wechselst du die Anwendung (z. B. Word -> Chrome), kommt eine Trennzeile in den Mitschnitt.
- Passwortfelder werden nicht mitgeschrieben (sofern 'uiautomation' installiert ist). Diese Erkennung ist nicht zu 100 % garantiert.

OPTION "ABSTURZSICHER" (standardmäßig AUS)
- Normal ist der gemerkte Text bei Absturz, Stromausfall oder Beenden weg.
- Eingeschaltet wird der Text in der Datei buffer.dat im TextRescue-Ordner gespeichert und nach einem Neustart wieder geladen.
- RISIKO: Der Text liegt dann (unverschlüsselt) auf der Festplatte und kann, selbst nach dem Löschen, durch Experten möglicherweise wiederhergestellt werden.
- Beim Ausschalten und bei "Jetzt löschen" wird buffer.dat gelöscht.

GEHEIMAGENTEN-MODUS
Das Icon wird in der Taskleiste ausgeblendet. TextRescue ist nicht mehr sichtbar und kann auch nicht mehr gesteuert werden. Selbst bei einem erneuten Start kommt das Icon nicht zurück. Erst durch ein erzwungenes Beenden über den Task-Manager (der Speicher wird dabei gelöscht, sofern nicht "Absturzsicher" aktiv ist) und einen Neustart, oder durch Eingabe der Tastenfolge #rescue#, wird das Menü wieder sichtbar.

VIRENSCANNER
Ein Programm, das alles Getippte mitliest, ist technisch dasselbe wie ein Keylogger. Windows Defender oder andere Scanner können TextRescue deshalb blockieren oder in Quarantäne verschieben. Das ist kein Fehler - du musst das Programm dann selbst als Ausnahme erlauben.

WAS SONST AUF DIE PLATTE KOMMT
Nur config.json mit deinen Einstellungen (kein getippter Text).
"""

_INFO_EN = """\
TextRescue - Quick info

WHAT IT DOES
TextRescue remembers what you type so you can get text back if a window crashes or you close it by accident. Controlled via the icon at the bottom right near the clock (right-click).

HOW IT WORKS
- By default the text is kept ONLY in memory and is NOT written to disk.
- It clears itself: after a set number of characters or after a set idle time (Options).
- Optionally mouse movement can also count as activity and delay the automatic clearing.
- "Pause clearing" turns timed clearing off completely; the arrow tip in the taskbar icon then turns red.
- When you switch applications (e.g. Word -> Chrome) a separator line is added.
- Password fields are not recorded (if 'uiautomation' is installed). This detection is not 100 % guaranteed.

"CRASH-SAFE" OPTION (off by default)
- Normally the stored text is lost on a crash, power loss or quit.
- When enabled, the text is stored in the file buffer.dat in the TextRescue folder and reloaded after a restart.
- RISK: the text then sits (unencrypted) on disk and may, even after deletion, be recoverable by experts.
- Turning it off and "Clear now" delete buffer.dat.

SECRET-AGENT MODE
The icon is hidden in the taskbar. TextRescue is no longer visible and cannot be controlled. Even after a restart the icon does not come back. It becomes visible again only by force-quitting via Task Manager (the buffer is cleared then, unless "Crash-safe" is on) and restarting, or by typing the sequence #rescue#.

ANTIVIRUS
A program that reads everything you type is technically the same as a keylogger. Windows Defender or other scanners may block or quarantine TextRescue. That is not a bug - you must allow it as an exception yourself.

WHAT ELSE GOES TO DISK
Only config.json with your settings (no typed text).
"""

TEXTS = {
    "de": {
        "menu_recover": "Öffnen",
        "menu_clear": "Jetzt löschen",
        "menu_options": "Optionen",
        "menu_info": "Info",
        "menu_pause": "Zeitgesteuertes Löschen pausieren",
        "menu_pause_active": "Löschen wieder aktivieren",
        "menu_quit": "Beenden",
        "recover_title": "TextRescue",
        "recover_empty": "(nichts gespeichert)",
        "copy_all": "Alles kopieren",
        "copied": "Kopiert.",
        "chars_suffix": "Zeichen",
        "options_title": "TextRescue - Optionen",
        "opt_max_chars": "Maximale Anzahl an Zeichen, die gespeichert werden:",
        "opt_a4": "(Das entspricht ca. {n} A4-Seiten.)",
        "opt_idle": "Nach dieser Anzahl an Minuten der Untätigkeit Speicher "
                    "automatisch löschen:",
        "opt_mouse": "Mausbewegung innerhalb des Zeitfensters verhindert die "
                     "Pausierung (zählt als Aktivität)",
        "opt_crashsafe": "Absturzsicher. Der Text wird im Verzeichnis von "
                         "TextRescue auf die Festplatte gespeichert. Dadurch "
                         "ist er nach einem Neustart, z. B. bei Stromausfall, "
                         "weiterhin verfügbar. Es besteht dadurch jedoch das "
                         "Risiko, dass der Text, selbst nach dem Löschen, durch "
                         "Experten möglicherweise wiederhergestellt werden kann.",
        "btn_clear_now": "Jetzt löschen",
        "confirm_clear": "Löschen bestätigen",
        "confirm_clear_opt": "Anhaken, um Mitschrift zu löschen",
        "opt_autostart": "Automatisch mit Windows starten",
        "minutes_unit": "Minuten",
        "btn_info": "Info",
        "btn_save": "Speichern",
        "btn_close": "Schließen",
        "lang_label": "Sprache / Language:",
        "saved": "Gespeichert.",
        "cleared": "Puffer geleert.",
        "paused_hint": "Zeitgesteuertes Löschen ist derzeit pausiert.",
        "avail_keyboard": "Tastatur mitlesen",
        "avail_tray": "Tray-Symbol",
        "avail_pw": "Passwortfeld-Schutz",
        "ok": "OK",
        "missing": "fehlt",
        "info_title": "TextRescue - Info / Hilfe",
        "info_body": _INFO_DE,
        "app_switch_fmt": "\n\n---- [{app}] {time} ----\n",
        "header_sub": "Zwischenspeicher für getippten Text",
        "credit_1": "Diese kostenlose Software wurde von ",
        "credit_name": "Christoph Puhl",
        "credit_2": " entwickelt und von Claude.ai umgesetzt.",
        "credit_3": "Wenn Du möchtest, kannst Du ",
        "credit_link": "hier",
        "credit_4": " gerne für einen Kaffee, ein Mohnbeugerl oder ein KI-Monatsabo spenden.",
        "credit3_1": "Dieses Projekt auf ",
        "credit3_github": "GitHub",
        "credit3_2": " ansehen. Mehr über den ",
        "credit3_author": "Autor",
        "credit3_3": ", weitere Apps, ",
        "credit3_comics": "Comics",
        "credit3_4": " und Tools findest Du auf ",
        "credit3_puhl": "puhl.ch",
        "credit3_5": ".",
        "opt_incognito": "Geheimagenten-Modus. Das Icon wird "
                         "in der Taskleiste ausgeblendet. TextRescue ist nicht "
                         "mehr sichtbar und kann auch nicht mehr gesteuert "
                         "werden. Selbst bei einem erneuten Start kommt das Icon "
                         "nicht zurück. Erst durch ein erzwungenes Beenden über "
                         "den Task-Manager (der Speicher wird dabei gelöscht, "
                         "sofern nicht \"Absturzsicher\" aktiv ist) und einen "
                         "Neustart, oder durch Eingabe der Tastenfolge #rescue#, "
                         "wird das Menü wieder sichtbar.",
    },
    "en": {
        "menu_recover": "Open",
        "menu_clear": "Clear now",
        "menu_options": "Options",
        "menu_info": "Info",
        "menu_pause": "Pause timed clearing",
        "menu_pause_active": "Resume clearing",
        "menu_quit": "Quit",
        "recover_title": "TextRescue",
        "recover_empty": "(nothing stored)",
        "copy_all": "Copy all",
        "copied": "Copied.",
        "chars_suffix": "characters",
        "options_title": "TextRescue - Options",
        "opt_max_chars": "Maximum number of characters to keep:",
        "opt_a4": "(That is about {n} A4 pages.)",
        "opt_idle": "Automatically clear the buffer after this many minutes "
                    "of inactivity:",
        "opt_mouse": "Mouse movement within the time window prevents clearing "
                     "(counts as activity)",
        "opt_crashsafe": "Crash-safe. The text is saved to disk in the "
                         "TextRescue folder. That way it is still available "
                         "after a restart, e.g. a power loss. However, this "
                         "brings the risk that the text, even after deletion, "
                         "may be recoverable by experts.",
        "btn_clear_now": "Clear now",
        "confirm_clear": "Confirm clearing",
        "confirm_clear_opt": "Tick to clear the transcript",
        "opt_autostart": "Start automatically with Windows",
        "minutes_unit": "minutes",
        "btn_info": "Info",
        "btn_save": "Save",
        "btn_close": "Close",
        "lang_label": "Sprache / Language:",
        "saved": "Saved.",
        "cleared": "Buffer cleared.",
        "paused_hint": "Timed clearing is currently paused.",
        "avail_keyboard": "Keystroke capture",
        "avail_tray": "Tray icon",
        "avail_pw": "Password-field guard",
        "ok": "OK",
        "missing": "missing",
        "info_title": "TextRescue - Info / Help",
        "info_body": _INFO_EN,
        "app_switch_fmt": "\n\n---- [{app}] {time} ----\n",
        "header_sub": "Buffer for typed text",
        "credit_1": "This free software was developed by ",
        "credit_name": "Christoph Puhl",
        "credit_2": " and implemented by Claude.ai.",
        "credit_3": "If you like, you can donate ",
        "credit_link": "here",
        "credit_4": " for a coffee, a pastry or an AI monthly subscription.",
        "credit3_1": "View this project on ",
        "credit3_github": "GitHub",
        "credit3_2": ". More about the ",
        "credit3_author": "author",
        "credit3_3": ", more apps, ",
        "credit3_comics": "comics",
        "credit3_4": " and tools at ",
        "credit3_puhl": "puhl.ch",
        "credit3_5": ".",
        "opt_incognito": "Secret-agent mode. The icon is "
                         "hidden in the taskbar. TextRescue is no longer visible "
                         "and cannot be controlled. Even after a restart the "
                         "icon does not come back. It becomes visible again only "
                         "by force-quitting via Task Manager (the buffer is "
                         "cleared then, unless \"Crash-safe\" is on) and "
                         "restarting, or by typing the sequence #rescue#.",
    },
}

# Feste Links fuer die Credit-/Spenden-Zeile
MAILTO_URL = "mailto:apps@puhl.ch"
DONATE_URL = "https://paypal.me/PuhlChristoph"
GITHUB_URL = "https://github.com/"          # wird gesetzt, sobald das Repo steht
AUTHOR_URL = "https://de.wikipedia.org/wiki/Christoph_Puhl"
COMICS_URL = "https://www.diezöno.se"
PUHL_URL = "https://www.puhl.ch"


# ===========================================================================
# Windows-API: aktives Fenster / Prozess / Passwortfeld / Mausposition
# ===========================================================================
def active_window_title() -> str:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or "unknown"
    except Exception:
        return "unknown"


def active_process_name() -> str:
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if not h:
            return active_window_title()
        buf = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, None, buf, 260)
        kernel32.CloseHandle(h)
        return buf.value or active_window_title()
    except Exception:
        return active_window_title()


def mouse_pos():
    try:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)
    except Exception:
        return None


def is_password_field_active() -> bool:
    if not HAVE_UIA:
        return False
    try:
        el = auto.GetFocusedControl()
        if el is None:
            return False
        return bool(getattr(el, "IsPassword", False)) or \
               getattr(el, "ControlTypeName", "") == "PasswordControl"
    except Exception:
        return False


import ctypes.wintypes  # nach Definitionen, fuer POINT


# ===========================================================================
# Pfade / Konfiguration
# ===========================================================================
def app_dir() -> str:
    """Ordner, in dem exe/Skript liegt - hier liegen config.json/buffer.dat."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    """Pfad zu mitgelieferten Ressourcen (Flaggen, Icons).
    In der PyInstaller-exe liegen --add-data-Dateien in sys._MEIPASS,
    nicht neben der exe - deshalb dort zuerst suchen."""
    base = getattr(sys, "_MEIPASS", app_dir())
    p = os.path.join(base, name)
    if os.path.exists(p):
        return p
    return os.path.join(app_dir(), name)


CONFIG_PATH = os.path.join(app_dir(), "config.json")
BUFFER_PATH = os.path.join(app_dir(), "buffer.dat")

# --- Autostart mit Windows (Registry Run-Key, nur fuer diesen Benutzer) -----
AUTOSTART_NAME = "TextRescue"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_command() -> str:
    """Befehl, der beim Windows-Start ausgefuehrt wird."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # Als Skript: pythonw.exe (ohne Konsolenfenster) + Skriptpfad
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def is_autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_READ) as k:
            try:
                winreg.QueryValueEx(k, AUTOSTART_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                  _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


@dataclass
class Config:
    max_chars: int = 10000
    max_idle_minutes: int = 10
    crash_safe: bool = False
    lang: str = "de"
    paused: bool = False
    mouse_counts: bool = False      # Mausbewegung zählt als Aktivität
    incognito: bool = False         # Tray-Icon ausblenden (Geheimagenten-Modus)

    @staticmethod
    def load() -> "Config":
        if os.path.exists(CONFIG_PATH):
            try:
                return Config(**json.load(open(CONFIG_PATH, "r", encoding="utf-8")))
            except Exception:
                pass
        return Config()

    def save(self) -> None:
        try:
            json.dump(asdict(self), open(CONFIG_PATH, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass


# ===========================================================================
# Absturzsicherung: Puffer als Datei (unverschluesselt)
# ===========================================================================
def wipe_persist_files():
    try:
        if os.path.exists(BUFFER_PATH):
            os.remove(BUFFER_PATH)
    except Exception:
        pass


# ===========================================================================
# Puffer
# ===========================================================================
class Buffer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.text = ""
        self.last_activity = time.time()
        self.lock = threading.Lock()
        self.last_app = None
        if cfg.crash_safe:
            self._load_from_disk()

    def _trim(self):
        if len(self.text) > self.cfg.max_chars:
            self.text = self.text[-self.cfg.max_chars:]

    def touch(self):
        self.last_activity = time.time()

    def mark_app(self, app: str):
        with self.lock:
            if app != self.last_app and self.text:
                fmt = TEXTS[self.cfg.lang]["app_switch_fmt"]
                self.text += fmt.format(app=app, time=time.strftime("%H:%M"))
                self._trim()
            self.last_app = app

    def add(self, ch: str):
        with self.lock:
            self.text += ch
            self._trim()
        self.touch()

    def backspace(self):
        with self.lock:
            self.text = self.text[:-1]
        self.touch()

    def forget(self):
        with self.lock:
            self.text = ""
        if self.cfg.crash_safe:
            self._save_to_disk()

    def snapshot(self) -> str:
        with self.lock:
            return self.text

    def maybe_expire(self):
        if self.cfg.paused:
            return
        if (time.time() - self.last_activity) >= self.cfg.max_idle_minutes * 60 \
                and self.text:
            self.forget()

    def _save_to_disk(self):
        if not self.cfg.crash_safe:
            return
        try:
            with open(BUFFER_PATH, "w", encoding="utf-8") as f:
                f.write(self.snapshot())
        except Exception:
            pass

    def _load_from_disk(self):
        if not os.path.exists(BUFFER_PATH):
            return
        try:
            with open(BUFFER_PATH, "r", encoding="utf-8") as f:
                self.text = f.read()
        except Exception:
            self.text = ""

    def periodic_persist(self):
        if self.cfg.crash_safe:
            self._save_to_disk()


# ===========================================================================
# Icon zeichnen (Pfeil gruen oder - wenn pausiert - rot)
# ===========================================================================
def make_icon_image(paused: bool):
    # Bevorzugt die sauberen, mitgelieferten Logo-PNGs (gruen / rot).
    name = "icon_paused.png" if paused else "icon.png"
    p = resource_path(name)
    if os.path.exists(p):
        try:
            return Image.open(p)
        except Exception:
            pass
    # Fallback: zur Laufzeit zeichnen (falls PNGs fehlen)
    import math
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    R = size * 0.31
    sw = int(size * 0.10)
    green = (26, 163, 51, 255)
    red = (210, 59, 59, 255)
    black = (27, 27, 27, 255)
    arrow_col = red if paused else green

    # Ringbogen mit großer Lücke rechts (von 38deg CCW herum bis -38deg)
    a0, a1 = 38, -38
    steps = 180
    pts = []
    for i in range(steps + 1):
        ang = math.radians(a0 + ((a1 + 360) - a0) * i / steps)
        pts.append((cx + R * math.cos(ang), cy + R * math.sin(ang)))
    d.line(pts, fill=green, width=sw, joint="curve")
    # runde Enden
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0]-sw/2, p[1]-sw/2, p[0]+sw/2, p[1]+sw/2], fill=green)

    # Pfeilspitze am oberen Lückenende (pts[-1]), in Laufrichtung
    ex, ey = pts[-1]; px, py = pts[-4]
    dx, dy = ex - px, ey - py
    L = math.hypot(dx, dy) or 1
    dx, dy = dx / L, dy / L
    nx, ny = -dy, dx
    half = sw * 1.15; length = sw * 1.9; overlap = sw * 0.4
    base = (ex - dx * overlap, ey - dy * overlap)
    tip = (base[0] + dx * (length + overlap), base[1] + dy * (length + overlap))
    b1 = (base[0] + nx * half, base[1] + ny * half)
    b2 = (base[0] - nx * half, base[1] - ny * half)
    d.polygon([tip, b1, b2], fill=arrow_col)

    # 4 Textzeilen in der Mitte
    for y, l in zip([0.37, 0.44, 0.56, 0.63], [0.20, 0.27, 0.27, 0.20]):
        yy = size * y
        d.line([(cx - size*l/2, yy), (cx + size*l/2, yy)], fill=black, width=int(size*0.045))

    return img


# ===========================================================================
# Modernes Fenster-Fundament
# ===========================================================================
def style_window(win):
    win.configure(bg=BG)
    try:
        win.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass


def setup_style(root):
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=FG)
    st.configure("Muted.TLabel", background=BG, foreground=MUTED)
    st.configure("Card.TLabel", background=CARD, foreground=FG)
    st.configure("Header.TLabel", background=BG, foreground=FG,
                 font=("Segoe UI Semibold", 15))
    st.configure("Sub.TLabel", background=BG, foreground=MUTED,
                 font=("Segoe UI", 9))
    st.configure("TButton", padding=(14, 7), font=("Segoe UI", 10))
    st.configure("Accent.TButton", padding=(16, 8))
    st.map("Accent.TButton",
           background=[("!disabled", ACCENT), ("active", "#245bc0")],
           foreground=[("!disabled", "white")])
    st.configure("TEntry", padding=4)
    st.configure("TCheckbutton", background=BG, foreground=FG)
    return st


# ===========================================================================
# GUI
# ===========================================================================
class Windows:
    def __init__(self, app):
        self.app = app
        self.root = tk.Tk()
        self.root.withdraw()
        setup_style(self.root)

    def t(self, key):
        return TEXTS[self.app.cfg.lang][key]

    def _toast(self, parent, msg):
        """Dezente Rückmeldung im Fenster statt Popup."""
        lbl = tk.Label(parent, text=msg, bg="#e7f6ec", fg="#176b2c",
                       font=("Segoe UI", 9), padx=10, pady=4)
        lbl.place(relx=0.5, rely=0.02, anchor="n")
        parent.after(1600, lbl.destroy)

    def _load_flag(self, filename):
        """Kleine Flaggen-PNG laden (auch aus der exe). None, wenn nicht da."""
        try:
            return tk.PhotoImage(file=resource_path(filename))
        except Exception:
            return None

    def show_recover(self):
        win = tk.Toplevel(self.root); style_window(win)
        win.title(self.t("recover_title"))
        win.attributes("-topmost", True)
        win.geometry("700x580")
        win.minsize(560, 420)

        head = ttk.Frame(win); head.pack(side="top", fill="x", padx=16, pady=(14, 6))
        ttk.Label(head, text="TextRescue", style="Header.TLabel").pack(side="left")
        cnt = ttk.Label(head, style="Sub.TLabel")
        cnt.pack(side="right")

        # Unten verankern, damit Buttons/Info IMMER sichtbar bleiben
        bar = ttk.Frame(win); bar.pack(side="bottom", fill="x", padx=16, pady=(6, 14))
        cwrap = ttk.Frame(win); cwrap.pack(side="bottom", fill="x", padx=16)
        self._credit_block(cwrap)

        # Textbereich fuellt den Rest
        wrap = tk.Frame(win, bg=CARD, highlightthickness=1,
                        highlightbackground="#e3e6ea")
        wrap.pack(side="top", fill="both", expand=True, padx=16, pady=6)
        txt = tk.Text(wrap, wrap="word", relief="flat", bg=CARD, fg=FG,
                      font=("Segoe UI", 10), padx=10, pady=10, borderwidth=0)
        content = self.app.buf.snapshot() or self.t("recover_empty")
        txt.insert("1.0", content)
        txt.pack(fill="both", expand=True)
        cnt.configure(text=f"{len(self.app.buf.snapshot())} {self.t('chars_suffix')}")

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(txt.get("1.0", "end-1c"))
            self._toast(win, self.t("copied"))

        ttk.Button(bar, text=self.t("copy_all"), style="Accent.TButton",
                   command=copy_all).pack(side="left")

        confirm = tk.BooleanVar(value=False)
        del_btn = ttk.Button(bar, text=self.t("btn_clear_now"), state="disabled")

        def do_clear():
            self.app.buf.forget()
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", self.t("recover_empty"))
            cnt.configure(text=f"0 {self.t('chars_suffix')}")
            confirm.set(False)
            del_btn.configure(state="disabled")
            self._toast(win, self.t("cleared"))

        del_btn.configure(command=do_clear)
        chk = ttk.Checkbutton(bar, text=self.t("confirm_clear"), variable=confirm,
                              command=lambda: del_btn.configure(
                                  state="normal" if confirm.get() else "disabled"))

        ttk.Button(bar, text=self.t("btn_close"),
                   command=win.destroy).pack(side="right")
        del_btn.pack(side="right", padx=(0, 8))
        chk.pack(side="right", padx=(0, 8))

    def show_info(self):
        win = tk.Toplevel(self.root); style_window(win)
        win.title(self.t("info_title"))
        win.attributes("-topmost", True)
        win.geometry("660x620")
        box = scrolledtext.ScrolledText(win, wrap="word", relief="flat",
                                        bg=CARD, fg=FG, font=("Segoe UI", 10),
                                        padx=12, pady=12, borderwidth=0)
        box.insert("1.0", self.t("info_body"))
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=16, pady=(16, 6))

        cwrap = ttk.Frame(win); cwrap.pack(fill="x", padx=16)
        self._credit_block(cwrap)

        ttk.Button(win, text=self.t("btn_close"), style="Accent.TButton",
                   command=win.destroy).pack(pady=(10, 14))

    def _credit_block(self, parent):
        """Credit/Spenden/Links als fliessender, umbrechender Text (ohne
        riesige Abstaende; lange Zeilen brechen automatisch um)."""
        box = tk.Text(parent, bg=NOTE_BG, fg=FG, bd=0, highlightthickness=0,
                      wrap="word", font=("Segoe UI", 9), cursor="arrow",
                      padx=10, pady=8, height=3)
        box.pack(fill="x", pady=(14, 0))

        self._credit_tag = 0

        def add(text):
            box.insert("end", text)

        def addlink(text, url):
            self._credit_tag += 1
            tag = "lnk%d" % self._credit_tag
            box.insert("end", text, (tag,))
            box.tag_config(tag, foreground=ACCENT, underline=1)
            box.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            box.tag_bind(tag, "<Enter>", lambda e: box.config(cursor="hand2"))
            box.tag_bind(tag, "<Leave>", lambda e: box.config(cursor="arrow"))

        t = self.t
        add(t("credit_1")); addlink(t("credit_name"), MAILTO_URL)
        add(t("credit_2") + "\n")
        add(t("credit_3")); addlink(t("credit_link"), DONATE_URL)
        add(t("credit_4") + "\n")
        add(t("credit3_1")); addlink(t("credit3_github"), GITHUB_URL)
        add(t("credit3_2")); addlink(t("credit3_author"), AUTHOR_URL)
        add(t("credit3_3")); addlink(t("credit3_comics"), COMICS_URL)
        add(t("credit3_4")); addlink(t("credit3_puhl"), PUHL_URL)
        add(t("credit3_5"))
        box.config(state="disabled")

        def fit(_=None):
            try:
                box.update_idletasks()
                dl = box.count("1.0", "end-1c", "displaylines")
                n = dl[0] if isinstance(dl, (tuple, list)) else dl
                box.config(height=max(3, (n or 3)))
            except Exception:
                box.config(height=4)
        box.bind("<Configure>", fit)
        box.after(60, fit)

    def _pause_bars(self, parent):
        """Kleines Canvas mit zwei roten vertikalen Balken (Pause-Symbol)."""
        c = tk.Canvas(parent, width=14, height=13, bg=BG, highlightthickness=0)
        c.create_rectangle(3, 1, 6, 12, fill=RED, outline=RED)
        c.create_rectangle(8, 1, 11, 12, fill=RED, outline=RED)
        return c

    def show_options(self, geo=None):
        win = tk.Toplevel(self.root); style_window(win)
        win.title(self.t("options_title"))
        win.attributes("-topmost", True)
        win.geometry(geo if geo else "640x720")
        win.minsize(560, 560)
        wrap_targets = []       # Widgets, deren Umbruch der Fensterbreite folgt

        def on_resize(e):
            if e.widget is win:
                w = max(320, win.winfo_width() - 80)
                for t in wrap_targets:
                    try:
                        t.configure(wraplength=w)
                    except Exception:
                        pass
        win.bind("<Configure>", on_resize)

        head = ttk.Frame(win); head.pack(side="top", fill="x", padx=18, pady=(16, 2))
        ttk.Label(head, text=self.t("options_title").split(" - ")[-1],
                  style="Header.TLabel").pack(side="left")

        # ----- unten verankern: Credits + eine Knopfreihe -----
        bottom = ttk.Frame(win); bottom.pack(side="bottom", fill="x",
                                             padx=18, pady=(0, 14))
        self._credit_block(bottom)

        bar = ttk.Frame(bottom); bar.pack(fill="x", pady=(12, 0))
        confirm_opt = tk.BooleanVar(value=False)
        del_opt = ttk.Button(bar, text=self.t("btn_clear_now"), state="disabled")

        def do_clear_opt():
            self.app.buf.forget()
            confirm_opt.set(False)
            del_opt.configure(state="disabled")
            self._toast(win, self.t("cleared"))
        del_opt.configure(command=do_clear_opt)

        # alle Buttons auf EINER Ebene: Haken | Löschen | Info ... Speichern
        tk.Checkbutton(bar, text=self.t("confirm_clear_opt"), variable=confirm_opt,
                       bg=BG, fg=FG, activebackground=BG,
                       command=lambda: del_opt.configure(
                           state="normal" if confirm_opt.get() else "disabled")
                       ).pack(side="left")
        del_opt.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text=self.t("btn_info"),
                   command=self.show_info).pack(side="left", padx=(12, 0))
        ttk.Button(bar, text=self.t("btn_save"), style="Accent.TButton",
                   command=lambda: save_close()).pack(side="right")

        # ----- oberer Inhaltsbereich -----
        body = ttk.Frame(win); body.pack(side="top", fill="both", expand=True,
                                         padx=18, pady=8)

        # --- Sprache: kompaktes Dropdown mit kleiner Flagge ---
        row = ttk.Frame(body); row.pack(fill="x", pady=(0, 10))
        ttk.Label(row, text=self.t("lang_label")).pack(side="left")

        def set_lang(code):
            if self.app.cfg.lang != code:
                self.app.cfg.lang = code; self.app.cfg.save()
                self.app.rebuild_tray()
                g = win.geometry(); win.destroy(); self.show_options(g)

        self._flag_de = self._load_flag("flag_de.png")
        self._flag_en = self._load_flag("flag_en.png")
        mb = tk.Menubutton(row, relief="solid", bd=1, bg=CARD, fg=FG,
                           padx=6, pady=1, cursor="hand2", font=("Segoe UI", 10))
        menu = tk.Menu(mb, tearoff=0)
        menu.add_command(label=" Deutsch", image=self._flag_de, compound="left",
                         command=lambda: set_lang("de"))
        menu.add_command(label=" Englisch", image=self._flag_en, compound="left",
                         command=lambda: set_lang("en"))
        mb.config(menu=menu)
        cur_img = self._flag_de if self.app.cfg.lang == "de" else self._flag_en
        cur_lbl = "Deutsch" if self.app.cfg.lang == "de" else "Englisch"
        mb.config(image=cur_img, text=" " + cur_lbl + " ▾", compound="left")
        mb._imgs = (self._flag_de, self._flag_en)
        mb.pack(side="left", padx=10)

        # --- Max Zeichen + A4 ---
        lmc = ttk.Label(body, text=self.t("opt_max_chars"), justify="left")
        lmc.pack(anchor="w"); wrap_targets.append(lmc)
        r2 = ttk.Frame(body); r2.pack(fill="x", pady=(2, 0))
        chars = tk.StringVar(value=str(self.app.cfg.max_chars))
        ttk.Entry(r2, textvariable=chars, width=12).pack(side="left")
        a4 = tk.StringVar()
        ttk.Label(r2, textvariable=a4, style="Muted.TLabel").pack(side="left", padx=10)

        def upd_a4(*_):
            try:
                n = max(0, int(chars.get()))
            except ValueError:
                a4.set(""); return
            a4.set(self.t("opt_a4").format(n=f"{n/CHARS_PER_A4:.1f}".replace(".", ",")))
        chars.trace_add("write", upd_a4); upd_a4()

        # --- Idle-Minuten + Einheit + (falls pausiert) Pause-Balken + Hinweis ---
        lid = ttk.Label(body, text=self.t("opt_idle"), justify="left")
        lid.pack(anchor="w", pady=(12, 2)); wrap_targets.append(lid)
        r3 = ttk.Frame(body); r3.pack(fill="x")
        mins = tk.StringVar(value=str(self.app.cfg.max_idle_minutes))
        ttk.Entry(r3, textvariable=mins, width=12).pack(side="left")
        ttk.Label(r3, text=self.t("minutes_unit"), style="Muted.TLabel"
                  ).pack(side="left", padx=10)
        if self.app.cfg.paused:
            self._pause_bars(r3).pack(side="left", padx=(12, 4))
            tk.Label(r3, text=self.t("paused_hint"), bg=BG, fg=RED,
                     font=("Segoe UI Semibold", 9)).pack(side="left")

        # --- Checkboxen mit Umbruch ---
        def wrap_check(var_val, key):
            v = tk.BooleanVar(value=var_val)
            cb = tk.Checkbutton(body, text=self.t(key), variable=v, bg=BG, fg=FG,
                                activebackground=BG, anchor="w", justify="left")
            cb.pack(anchor="w", pady=(12, 0)); wrap_targets.append(cb)
            return v

        mouse = wrap_check(self.app.cfg.mouse_counts, "opt_mouse")
        autostart = wrap_check(is_autostart_enabled(), "opt_autostart")
        crash = wrap_check(self.app.cfg.crash_safe, "opt_crashsafe")
        incognito = wrap_check(self.app.cfg.incognito, "opt_incognito")

        # --- Statuszeile ---
        ok = self.t("ok"); miss = self.t("missing")
        stat = (f"{self.t('avail_keyboard')}: {ok if HAVE_KEYBOARD else miss}   "
                f"{self.t('avail_tray')}: {ok if HAVE_TRAY else miss}   "
                f"{self.t('avail_pw')}: {ok if HAVE_UIA else miss}")
        ttk.Label(body, text=stat, style="Muted.TLabel").pack(anchor="w", pady=(14, 0))

        def save_close():
            try:
                self.app.cfg.max_chars = max(100, int(chars.get()))
                self.app.cfg.max_idle_minutes = max(1, int(mins.get()))
            except ValueError:
                self._toast(win, "0-9"); return
            self.app.cfg.mouse_counts = mouse.get()
            was = self.app.cfg.crash_safe
            now = crash.get()
            self.app.cfg.crash_safe = now
            was_incog = self.app.cfg.incognito
            self.app.cfg.incognito = incognito.get()
            self.app.cfg.save()
            if now and not was:
                self.app.buf._save_to_disk()
            if was and not now:
                wipe_persist_files()
            set_autostart(autostart.get())
            # Geheimagenten-Modus: Icon aus-/einblenden
            if self.app.cfg.incognito and not was_incog:
                self.app.hide_tray()
            elif not self.app.cfg.incognito and was_incog:
                self.app.show_tray()
            self._toast(win, self.t("saved"))
            win.after(700, win.destroy)

    def run(self):
        self.root.mainloop()


# ===========================================================================
# App
# ===========================================================================
class App:
    def __init__(self):
        self.cfg = Config.load()
        self.buf = Buffer(self.cfg)
        self.gui = Windows(self)
        self.icon = None
        self._last_mouse = mouse_pos()
        self._seq = ""              # Tastenfolge-Erkennung (#rescue#)
        self._install_hook()
        if not self.cfg.incognito:  # im Geheimagenten-Modus kein Icon anzeigen
            self._start_tray()
        self._tick()

    def _install_hook(self):
        if HAVE_KEYBOARD:
            keyboard.on_press(self._on_key)

    def _check_sequence(self, ch):
        """Erkennt die Tastenfolge #rescue#, um den Geheimagenten-Modus zu beenden."""
        self._seq = (self._seq + ch)[-10:]
        if self._seq.endswith("#rescue#"):
            self._seq = ""
            if self.cfg.incognito:
                self.cfg.incognito = False
                self.cfg.save()
                self.gui.root.after(0, self.show_tray)

    def _on_key(self, event):
        if is_password_field_active():
            return
        self.buf.mark_app(active_process_name())
        name = event.name
        if name == "space":
            self.buf.add(" "); self._check_sequence(" "); return
        if name == "enter":
            self.buf.add("\n"); return
        if name == "tab":
            self.buf.add("\t"); return
        if name == "backspace":
            self.buf.backspace(); return
        ch = char_from_event(event)
        if ch:
            self.buf.add(ch)
            self._check_sequence(ch)

    def _make_icon_image(self):
        return make_icon_image(self.cfg.paused)

    def _menu(self):
        T = TEXTS[self.cfg.lang]
        R = self.gui.root

        def toggle_pause(i, it):
            self.cfg.paused = not self.cfg.paused
            self.cfg.save(); self.rebuild_tray()

        # Wenn pausiert: Pause-Symbol statt Haken vor dem Eintrag.
        if self.cfg.paused:
            pause_text = "⏸ " + T["menu_pause_active"]
        else:
            pause_text = T["menu_pause"]

        return pystray.Menu(
            pystray.MenuItem(T["menu_recover"],
                             lambda i, it: R.after(0, self.gui.show_recover),
                             default=True),
            pystray.MenuItem(pause_text, toggle_pause),
            pystray.MenuItem(T["menu_options"],
                             lambda i, it: R.after(0, self.gui.show_options)),
            pystray.MenuItem(T["menu_info"],
                             lambda i, it: R.after(0, self.gui.show_info)),
            pystray.MenuItem(T["menu_quit"],
                             lambda i, it: (i.stop(), R.after(0, R.quit))),
        )

    def _start_tray(self):
        if not HAVE_TRAY:
            return
        self.icon = pystray.Icon("TextRescue", self._make_icon_image(),
                                 "TextRescue", self._menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

    def rebuild_tray(self):
        if self.icon is not None:
            try:
                self.icon.icon = self._make_icon_image()   # Farbe (rot/gruen)
                self.icon.menu = self._menu()
                self.icon.update_menu()
            except Exception:
                pass

    def hide_tray(self):
        """Geheimagenten-Modus: Icon aus der Taskleiste entfernen."""
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def show_tray(self):
        """Icon wieder anzeigen (nach #rescue# oder Deaktivieren)."""
        if self.icon is None and HAVE_TRAY:
            self._start_tray()

    def _tick(self):
        # Mausbewegung als Aktivität werten, wenn aktiviert
        if self.cfg.mouse_counts:
            p = mouse_pos()
            if p and p != self._last_mouse:
                self.buf.touch()
            self._last_mouse = p
        self.buf.maybe_expire()
        self.buf.periodic_persist()
        self.gui.root.after(1000, self._tick)

    def run(self):
        self.gui.run()


_SINGLE_INSTANCE_HANDLE = None


def already_running() -> bool:
    """True, wenn bereits eine TextRescue-Instanz laeuft (Windows-Mutex)."""
    global _SINGLE_INSTANCE_HANDLE
    try:
        kernel32 = ctypes.windll.kernel32
        _SINGLE_INSTANCE_HANDLE = kernel32.CreateMutexW(
            None, False, "TextRescue_SingleInstance_Mutex")
        return kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


if __name__ == "__main__":
    if already_running():
        sys.exit(0)        # zweite Instanz sofort beenden
    App().run()
