"""Colours, type and the stylesheet. The surfaces themselves are painted glass (glass.py):
this sheet only styles what sits on them, in white at different strengths."""

BG = "#07080b"
SURFACE = "#11141b"
RAISED = "#1a1e27"
TILE = "#141823"
BORDER = "#2a2f3a"
TEXT = "#f3f5f9"
MUTED = "#9ba2b3"
DIM = "#697083"
# One accent, and barely a colour: the white of the glass's own highlight with a breath of
# blue. Colour is left to the game behind the glass and to the few things that mean
# something: state (good, warn, bad) and each unit slot.
ACCENT = "#d9e4ff"
ACCENT_HOVER = "#ffffff"
ACCENT_SOFT = "#262b36"
GOOD = "#7fe0b5"
WARN = "#f2c879"
BAD = "#ff8c8c"
SLOT_COLORS = {1: "#a9b8ff", 2: "#ff9aa5", 3: "#86e3d7", 4: "#f6cf8a", 5: "#a9e39a", 6: "#f3a9e2"}
STATE_COLORS = {"Running": GOOD, "Paused": WARN, "Starting": ACCENT, "Idle": "#8a91a3", "Stopping": BAD}
ICON_FONT = "Segoe Fluent Icons"
CHEVRON = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),
                                     "assets", "chevron.svg").replace("\\", "/")
# Bahnschrift: Windows' own DIN-style face. Numbers and titles in it read like an instrument,
# which suits a macro watching a game; running text stays in Segoe UI.
DISPLAY = "Bahnschrift"

# Segoe Fluent Icons glyphs
ICONS = {
    "game": "", "main": "", "tasks": "", "config": "", "extras": "",
    "about": "", "play": "", "pause": "", "stop": "", "link": "",
    "send": "", "gift": "", "camera": "", "folder": "", "logs": "",
    "match": "", "trophy": "", "session": "", "keys": "", "warn": "",
    "check": "", "chevron": "", "map": "", "order": "", "view": "",
    "notes": "", "safety": "", "hook": "", "unit": "", "add": "",
    "unlink": "", "sync": "", "info": "", "clock": "", "minimize": "",
    "close": "",
}

# Glass edges in a stylesheet: light falls from above, so a control's top border is its
# bright rim and its bottom border the faint far side.
RIM = ("border-top: 1px solid rgba(255, 255, 255, 0.30); border-left: 1px solid rgba(255, 255, 255, 0.14); "
       "border-right: 1px solid rgba(255, 255, 255, 0.10); border-bottom: 1px solid rgba(255, 255, 255, 0.06);")
RIM_HOVER = ("border-top: 1px solid rgba(255, 255, 255, 0.48); border-left: 1px solid rgba(255, 255, 255, 0.22); "
             "border-right: 1px solid rgba(255, 255, 255, 0.16); border-bottom: 1px solid rgba(255, 255, 255, 0.10);")
# A well: a recess in the glass, for fields and lists. Its lower lip catches the light.
WELL = ("background: rgba(0, 0, 0, 0.26); border: 1px solid rgba(255, 255, 255, 0.07); "
        "border-bottom: 1px solid rgba(255, 255, 255, 0.12);")
SOFT = "rgba(235, 240, 250, 0.62)"

QSS = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; color: {TEXT}; outline: 0; }}
QWidget#root, QWidget#sub {{ background: transparent; }}
QFrame#card, QFrame#tile {{ background: transparent; border: 0; }}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-family: '{DISPLAY}'; font-size: 16px; font-weight: 600; color: #ffffff; letter-spacing: 0.4px; }}
QLabel#head {{ font-family: '{DISPLAY}'; font-size: 11px; font-weight: 400; color: rgba(235, 240, 250, 0.52); letter-spacing: 1.3px; }}
QLabel#big {{ font-family: '{DISPLAY}'; font-size: 18px; font-weight: 600; color: #ffffff; }}
QLabel#value {{ font-family: '{DISPLAY}'; font-size: 25px; font-weight: 600; color: #ffffff; }}
QLabel#muted {{ color: {SOFT}; font-size: 12px; }}
QLabel#dim {{ color: rgba(235, 240, 250, 0.40); font-size: 12px; }}
QLabel#row {{ color: rgba(243, 245, 249, 0.92); font-size: 13px; }}
QLabel#section {{ color: rgba(235, 240, 250, 0.45); font-size: 11px; letter-spacing: 1px; }}
QLabel#subtitle {{ font-family: '{DISPLAY}'; font-size: 22px; font-weight: 600; color: #ffffff; }}
QLabel#navtitle {{ font-size: 14px; font-weight: 600; color: #ffffff; }}
QLabel#navsub {{ font-size: 11px; color: rgba(235, 240, 250, 0.52); }}
QLabel#chip {{ background: rgba(255, 255, 255, 0.07); {RIM} border-radius: 9px; padding: 4px 10px; font-size: 12px; color: #ffffff; }}
QLabel#key {{ background: rgba(255, 255, 255, 0.07); {RIM} border-radius: 7px;
    font-family: 'Cascadia Mono', 'Consolas'; font-size: 11px; font-weight: 600; padding: 1px 0; color: #ffffff; }}
QPushButton {{ background: rgba(255, 255, 255, 0.07); {RIM} border-radius: 10px; padding: 8px 14px; font-size: 13px; }}
QPushButton:hover {{ background: rgba(255, 255, 255, 0.12); {RIM_HOVER} }}
QPushButton:pressed {{ background: rgba(255, 255, 255, 0.04); }}
QPushButton:disabled {{ color: rgba(235, 240, 250, 0.30); background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.05); }}
QPushButton#primary {{ background: rgba(246, 248, 252, 0.93); border: 1px solid #ffffff;
    border-bottom: 1px solid rgba(255, 255, 255, 0.55); color: #0b0d12; font-weight: 600; font-size: 14px; padding: 10px; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#primary:pressed {{ background: rgba(226, 231, 240, 0.88); }}
QPushButton#primary:disabled {{ background: rgba(255, 255, 255, 0.06); color: rgba(235, 240, 250, 0.30);
    border: 1px solid rgba(255, 255, 255, 0.07); }}
QPushButton#danger {{ background: rgba(255, 110, 110, 0.10); border: 1px solid rgba(255, 140, 140, 0.30);
    border-bottom: 1px solid rgba(255, 140, 140, 0.12); color: {BAD}; font-weight: 600; padding: 10px; }}
QPushButton#danger:hover {{ background: rgba(255, 110, 110, 0.18); border: 1px solid rgba(255, 160, 160, 0.5); }}
QPushButton#danger:disabled {{ background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.05);
    color: rgba(235, 240, 250, 0.30); }}
QPushButton#nav {{ background: transparent; border: 1px solid transparent; border-radius: 12px; padding: 0; text-align: left; }}
QPushButton#nav:hover {{ background: rgba(255, 255, 255, 0.07); {RIM} }}
QPushButton#nav:pressed {{ background: rgba(255, 255, 255, 0.03); }}
QPushButton#hotkey {{ text-align: left; background: transparent; border: 0; border-radius: 8px; padding: 0; }}
QPushButton#hotkey:hover {{ background: rgba(255, 255, 255, 0.07); }}
QPushButton#chrome, QPushButton#close {{ background: transparent; border: 0; border-radius: 15px; font-family: '{ICON_FONT}';
    font-size: 10px; min-width: 34px; max-width: 34px; min-height: 30px; padding: 0; color: rgba(235, 240, 250, 0.75); }}
QPushButton#chrome:hover {{ background: rgba(255, 255, 255, 0.12); color: #ffffff; }}
QPushButton#close:hover {{ background: rgba(255, 105, 105, 0.85); color: #ffffff; }}
QPushButton#small {{ padding: 3px 11px; font-size: 12px; border-radius: 9px; }}
QPushButton#slot {{ text-align: left; padding: 6px 10px; font-size: 13px; }}
QPushButton#slot:checked {{ background: rgba(255, 255, 255, 0.16); {RIM_HOVER} }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ {WELL} border-radius: 9px;
    padding: 5px 9px; min-height: 22px; font-size: 13px; selection-background-color: rgba(217, 228, 255, 0.35); }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border: 1px solid rgba(255, 255, 255, 0.16); }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border: 1px solid rgba(217, 228, 255, 0.55); }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox::down-arrow {{ image: url({CHEVRON}); width: 11px; height: 11px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: 0; }}
QSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{ image: none; width: 0; height: 0; }}
QComboBox QAbstractItemView {{ background: #161a22; border: 1px solid rgba(255, 255, 255, 0.14);
    selection-background-color: rgba(255, 255, 255, 0.12); padding: 4px; font-size: 13px; }}
QListWidget {{ {WELL} border-radius: 12px; padding: 4px; font-size: 13px; }}
QListWidget::item {{ padding: 8px 8px; border-radius: 8px; margin: 1px 0; }}
QListWidget::item:hover {{ background: rgba(255, 255, 255, 0.06); }}
QListWidget::item:selected {{ background: rgba(255, 255, 255, 0.13); color: #ffffff; }}
QPlainTextEdit {{ {WELL} border-radius: 12px; color: rgba(225, 231, 243, 0.80);
    font-family: 'Cascadia Mono', 'Consolas'; font-size: 12px; padding: 6px; selection-background-color: rgba(217, 228, 255, 0.3); }}
QPlainTextEdit#logview {{ background: transparent; border: 0; padding: 0 2px 0 0;
    font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 12px; color: #dfe4ee; }}
QCheckBox {{ spacing: 10px; font-size: 13px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 6px; background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.20); }}
QCheckBox::indicator:hover {{ border: 1px solid rgba(255, 255, 255, 0.40); }}
QCheckBox::indicator:checked {{ background: rgba(246, 248, 252, 0.92); border: 1px solid #ffffff; }}
QFormLayout QLabel {{ color: {SOFT}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 0.16); border-radius: 2px; min-height: 26px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.30); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{ background: #171b23; color: {TEXT}; border: 1px solid rgba(255, 255, 255, 0.16); padding: 6px; font-size: 12px; }}
"""
