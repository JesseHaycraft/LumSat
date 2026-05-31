"""A calm, dark theme for the app.

Photo editors should let the photo be the brightest thing on screen, so the
chrome is a set of neutral dark grays with a single restrained accent color for
interactive highlights. Applied once as a Qt style sheet (QSS) at startup.
"""

# Single accent color, used sparingly for selection and hover states.
ACCENT = "#4a9eda"

STYLESHEET = f"""
QWidget {{
    background-color: #2b2b2b;
    color: #d8d8d8;
    font-size: 13px;
}}

/* Panels get a slightly different shade so zones read as distinct. */
QFrame#Panel {{
    background-color: #262626;
    border: none;
}}

QLabel#Heading {{
    color: #9a9a9a;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 4px 2px;
}}

QPushButton {{
    background-color: #3a3a3a;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 7px 12px;
}}
QPushButton:hover {{
    background-color: #444444;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: #303030;
}}
QPushButton:disabled {{
    color: #6a6a6a;
    border-color: #3a3a3a;
}}

/* The two primary actions, Import and Export, get the accent fill. */
QPushButton#Primary {{
    background-color: {ACCENT};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background-color: #5aaee8;
}}

QComboBox, QLineEdit, QSpinBox {{
    background-color: #333333;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox:hover, QLineEdit:focus {{
    border-color: {ACCENT};
}}

QListWidget {{
    background-color: #232323;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 4px;
    margin: 3px;
    padding: 3px;
}}
QListWidget::item:selected {{
    background-color: {ACCENT};
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: #4a4a4a;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}

QScrollBar:vertical {{
    background: #262626;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4a4a4a;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}

QSplitter::handle {{
    background-color: #1e1e1e;
}}
"""
