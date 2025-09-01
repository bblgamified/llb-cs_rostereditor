#!/usr/bin/env python3
"""
LLB Roster & Team Color Editor (PySide6)
=======================================
Edits one team at a time in "Little League Baseball: Championship Series" (NES).

Verified player row layout after 6-char name (bytes are offsets within the 16-byte row):
 6 : Hand/Size (00=R Tall,01=R Fat,02=R Short,80=L Tall,81=L Fat,82=L Short)
 7 : Buffer (FF)
 8 : UNK8 (unknown; keep editable)
 9 : ARM Power (defensive throwing)
10 : RUN SPEED
11 : HIT (stored 0–4; UI shows +1)
12 : PI (pitcher profile: 00=None, 08=Prof#1, 10=Prof#2, 18=Prof#3)
13 : Buffer
14 : Const14 (team constant / small scaler; often 0x02)
15 : Buffer

Pitcher profiles (3×8 bytes) begin after the all-FF padding line that ends the roster rows:
  • Profile #1 = bytes 8..15 of first 16-byte row after FF
  • Profile #2 = bytes 0..7  of second row
  • Profile #3 = bytes 8..15 of second row
Profile byte meanings (partial):
  byte0: top bit = hand (0x80 left), low nibble delivery (0=Normal,1=Hard,2=Sidearm)
  byte1=Stamina, byte2=Quality/Movement, byte3=Tune(0–15), byte6=Displayed Pitch skill(0–4), byte7=Mult(00/02)

New in this version:
 • Team dropdown wired to full offset map (16 teams)
 • Removed Throw Hand column (no standalone byte; bat side mirrors throw hand)
 • New "Team Colors" tab to edit two primary colors per team via the LLB palette
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import os

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QComboBox,
    QMessageBox, QSpinBox, QTabWidget, QFrame
)
from PySide6.QtGui import QColor, QPalette

NAME_LEN = 6
ROW_LEN  = 16

# --- Team offsets (roster start) ---
TEAM_OFFSETS = {
    "Japan":         0x10430,
    "Arizona":       0x10550,
    "Pennsylvania":  0x10670,
    "Chinese Taipei":0x10790,
    "Korea":         0x108B0,
    "New York":      0x109D0,
    "California":    0x10AF0,
    "Texas":         0x10C10,
    "Hawaii":        0x10D30,
    "Spain":         0x10E50,
    "Puerto Rico":   0x10F50,
    "Mexico":        0x11090,
    "Canada":        0x111B0,
    "Italy":         0x112D0,
    "Illinois":      0x113F0,
    "Florida":       0x11510,
}

# --- Team color offsets (two bytes per team: primary, secondary) ---
TEAM_OFFSETS_COLOUR = {
    "Japan":         0x1FAD0,
    "Arizona":       0x1FAD3,
    "Pennsylvania":  0x1FAD6,
    "Chinese Taipei":0x1FAD9,
    "Korea":         0x1FADC,
    "New York":      0x1FADF,
    "California":    0x1FAE2,
    "Texas":         0x1FAE5,
    "Hawaii":        0x1FAE8,
    "Spain":         0x1FAEB,
    "Puerto Rico":   0x1FAEE,
    "Mexico":        0x1FAF1,
    "Canada":        0x1FAF4,
    "Italy":         0x1FAF7,
    "Illinois":      0x1FAFA,
    "Florida":       0x1FAFD,
}

# Body mapping (byte 6)
BODY_TYPE_MAP = {
    0x00: "Right Tall",
    0x01: "Right Fat",
    0x02: "Right Short",
    0x80: "Left Tall",
    0x81: "Left Fat",
    0x82: "Left Short",
}
SIZE_FROM_CODE = {0: "Tall", 1: "Fat", 2: "Short"}
CODE_FROM_SIZE = {v: k for k, v in SIZE_FROM_CODE.items()}
PI_CHOICES   = [0x00, 0x08, 0x10, 0x18]
CONST14_CHOICES = [0x00, 0x02, 0x03, 0x04]

# NES LLB palette: value is HSV as "H,S,V" (H 0..360, S/V 0..255). Some S/V values may be out-of-range in source; we clamp.
LLB_COLOR_PALETTE_MAP = {
    0x00: "0,0,116", 0x01: "246,211,140", 0x02: "240,255,168", 0x03: "266,255,156",
    0x04: "310,255,140", 0x05: "354,255,168", 0x06: "0,255,164", 0x07: "3,255,124",
    0x08: "41,255,64", 0x09: "120,255,68", 0x0A: "120,255,80", 0x0B: "140,255,60",
    0x0C: "208,188,92", 0x0D: "0,0,0", 0x0E: "0,0,0", 0x0F: "0,0,0",
    0x10: "0,0,188", 0x11: "211,255,236", 0x12: "232,220,236", 0x13: "272,255,240",
    0x14: "300,255,188", 0x15: "336,255,228", 0x16: "11,255,216", 0x17: "20,240,200",
    0x18: "49,255,136", 0x19: "120,255,148", 0x1A: "120,255,168", 0x1B: "143,255,144",
    0x1C: "183,255,136", 0x1D: "0,0,0", 0x1E: "0,0,0", 0x1F: "0,0,0",
    0x20: "0,0,252", 0x21: "200,194,252", 0x22: "219,162,252", 0x23: "275,117,252",
    0x24: "296,134,252", 0x25: "331,138,252", 0x26: "7,158,252", 0x27: "29,198,252",
    0x28: "42,191,240", 0x29: "85,235,208", 0x2A: "118,172,220", 0x2B: "144,165,248",
    0x2C: "175,255,232", 0x2D: "0,0,120", 0x2E: "0,0,0", 0x2F: "0,0,0",
    0x30: "0,0,252", 0x31: "197,85,252", 0x32: "222,57,252", 0x33: "253,53,252",
    0x34: "300,57,252", 0x35: "338,57,252", 0x36: "9,77,252", 0x37: "34,85,252",
    0x38: "44,93,252", 0x39: "78,93,252", 0x3A: "136,77,240", 0x3B: "142,77,252",
    0x3C: "172,97,252", 0x3D: "0,0,196", 0x3E: "0,0,0", 0x3F: "0,0,0",
}

# ---- Data classes ----
@dataclass
class Player:
    name: str
    body_type: int   # byte6
    unk8: int        # byte8
    arm: int         # byte9
    speed: int       # byte10
    hit: int         # byte11 (0–4)
    pi: int          # byte12 (00/08/10/18)
    const14: int     # byte14
    row_offset: int

@dataclass
class PitchProfile:
    offset: int         # absolute ROM offset of first byte of the 8-byte profile
    raw: bytearray      # exactly 8 bytes

    @property
    def hand(self) -> str:
        return "Left" if (self.raw[0] & 0x80) else "Right"
    @hand.setter
    def hand(self, val: str):
        self.raw[0] = (self.raw[0] & 0x7F) | (0x80 if val == "Left" else 0)

    @property
    def delivery(self) -> str:
        low = self.raw[0] & 0x0F
        return {0: "Normal", 1: "Hard", 2: "Sidearm"}.get(low, f"0x{low:02X}")
    @delivery.setter
    def delivery(self, val: str):
        low = {"Normal":0, "Hard":1, "Sidearm":2}.get(val, 0)
        self.raw[0] = (self.raw[0] & 0xF0) | low

    @property
    def stamina(self) -> int: return self.raw[1]
    @stamina.setter
    def stamina(self, v: int): self.raw[1] = max(0, min(255, v))

    @property
    def quality(self) -> int: return self.raw[2]
    @quality.setter
    def quality(self, v: int): self.raw[2] = max(0, min(255, v))

    @property
    def tune(self) -> int: return self.raw[3]
    @tune.setter
    def tune(self, v: int): self.raw[3] = max(0, min(15, v))

    @property
    def skill(self) -> int: return self.raw[6]
    @skill.setter
    def skill(self, v: int): self.raw[6] = max(0, min(4, v))

    @property
    def mult(self) -> int: return self.raw[7]
    @mult.setter
    def mult(self, v: int): self.raw[7] = v & 0xFF

# ---- Model ----
class RosterModel:
    def __init__(self, rom_path: str, start_offset: int):
        self.rom_path = rom_path
        with open(rom_path, 'rb') as f:
            self.buf = bytearray(f.read())
        self.start = start_offset
        self.players: List[Player] = []
        self.profiles: List[PitchProfile] = []
        self._parse_team()
        self._parse_profiles()

    @staticmethod
    def _encode_name6(s: str) -> bytes:
        s = (s or '').upper()[:NAME_LEN]
        b = s.encode('ascii', 'ignore')
        if len(b) < NAME_LEN:
            b += b" " * (NAME_LEN - len(b))
        return b

    def _parse_player(self, chunk: bytes, offset: int) -> Optional[Player]:
        if len(chunk) != ROW_LEN:
            return None
        name_b = chunk[:NAME_LEN]
        if 0x00 in name_b:
            name_b = name_b.split(b" ", 1)[0]
        name = name_b.decode('ascii','ignore').rstrip(' ')
        attrs = chunk[NAME_LEN:]
        body_type = attrs[0]
        unk8      = attrs[2]
        arm       = attrs[3]
        speed     = attrs[4]
        hit       = attrs[5]
        pi        = attrs[6]
        const14   = attrs[8]
        return Player(name, body_type, unk8, arm, speed, hit, pi, const14, offset)

    def _parse_team(self) -> None:
        self.players.clear()
        cursor = self.start
        while cursor + ROW_LEN <= len(self.buf):
            row = self.buf[cursor:cursor+ROW_LEN]
            if all(b == 0xFF for b in row):
                break
            p = self._parse_player(row, cursor)
            if not p:
                break
            self.players.append(p)
            cursor += ROW_LEN

    def _find_ff_line_after_team(self) -> Optional[int]:
        cursor = self.start
        for _ in range(0x800 // 16):
            if cursor + 16 > len(self.buf):
                return None
            line = self.buf[cursor:cursor+16]
            if all(b == 0xFF for b in line):
                return cursor
            cursor += 16
        return None

    def _parse_profiles(self) -> None:
        self.profiles.clear()
        ff_line = self._find_ff_line_after_team()
        if ff_line is None:
            return
        base = ff_line + 16
        if base + 32 > len(self.buf):
            return
        row1 = self.buf[base: base+16]
        row2 = self.buf[base+16: base+32]
        p1 = bytearray(row1[8:16]); p1_off = base + 8
        p2 = bytearray(row2[0:8]);  p2_off = base + 16
        p3 = bytearray(row2[8:16]); p3_off = base + 24
        self.profiles = [PitchProfile(p1_off,p1), PitchProfile(p2_off,p2), PitchProfile(p3_off,p3)]

    # --- Team colors ---
    def read_team_colors(self, team_name: str) -> Optional[Tuple[int,int]]:
        off = TEAM_OFFSETS_COLOUR.get(team_name)
        if off is None: return None
        if off + 1 >= len(self.buf): return None
        return self.buf[off], self.buf[off+1]

    def write_team_colors(self, team_name: str, primary_idx: int, secondary_idx: int) -> None:
        off = TEAM_OFFSETS_COLOUR.get(team_name)
        if off is None: return
        if off + 1 >= len(self.buf): return
        self.buf[off]   = primary_idx & 0xFF
        self.buf[off+1] = secondary_idx & 0xFF

    def apply_players(self, players: List[Player]) -> None:
        self.players = players
        for p in players:
            row = bytearray(self.buf[p.row_offset:p.row_offset+ROW_LEN])
            row[:NAME_LEN]   = self._encode_name6(p.name)
            row[NAME_LEN+0]  = p.body_type   # byte6
            row[NAME_LEN+1]  = 0xFF          # byte7 buffer
            row[NAME_LEN+2]  = p.unk8        # byte8
            row[NAME_LEN+3]  = p.arm         # byte9
            row[NAME_LEN+4]  = p.speed       # byte10
            row[NAME_LEN+5]  = max(0, min(4, p.hit))  # byte11
            row[NAME_LEN+6]  = p.pi if p.pi in PI_CHOICES else 0x00  # byte12
            # byte13 buffer preserved
            row[NAME_LEN+8]  = p.const14     # byte14
            # byte15 preserved
            self.buf[p.row_offset:p.row_offset+ROW_LEN] = row

    def apply_profiles(self, profiles: List[PitchProfile]) -> None:
        self.profiles = profiles
        for pr in profiles:
            self.buf[pr.offset:pr.offset+8] = pr.raw

    def save_rom(self, out_path: str):
        with open(out_path,'wb') as f:
            f.write(self.buf)

# ---- UI helpers ----
def hsv_string_to_qcolor(s: str) -> QColor:
    try:
        h_str, s_str, v_str = s.split(',')
        h = int(float(h_str)) % 360
        sat = max(0, min(255, int(float(s_str))))
        val = max(0, min(255, int(float(v_str))))
        return QColor.fromHsv(h, sat, val)
    except Exception:
        return QColor(0,0,0)

def make_swatch(color: QColor, w: int = 36, h: int = 16) -> QFrame:
    f = QFrame()
    f.setFixedSize(w, h)
    f.setFrameShape(QFrame.Panel)
    f.setFrameShadow(QFrame.Sunken)
    pal = f.palette()
    pal.setColor(QPalette.Window, color)
    f.setAutoFillBackground(True)
    f.setPalette(pal)
    return f

# ---- UI ----
class EditorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLB Roster & Team Color Editor")
        self.model: Optional[RosterModel] = None
        self.loaded_team: Optional[str] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        # Top bar with team dropdown
        top = QHBoxLayout()
        self.rom_edit = QLineEdit(); self.rom_edit.setPlaceholderText("ROM file")
        browse = QPushButton("Browse"); browse.clicked.connect(self.on_browse)
        self.team_combo = QComboBox()
        # Populate in requested map order
        for name in TEAM_OFFSETS.keys():
            self.team_combo.addItem(name)
        self.team_combo.setEnabled(False)
        load = QPushButton("Load Team"); load.clicked.connect(self.on_load_selected_team)
        top.addWidget(QLabel("ROM:")); top.addWidget(self.rom_edit); top.addWidget(browse)
        top.addWidget(QLabel("Team:")); top.addWidget(self.team_combo); top.addWidget(load)
        root.addLayout(top)

        # Tabs
        self.tabs = QTabWidget()

        # Roster tab (no Throw Hand column; bat side mirrors throw hand per byte6)
        self.roster_table = QTableWidget(0, 9)
        self.roster_table.setHorizontalHeaderLabels([
            "Name", "Bat Side", "Body Size",
            "Skill(0-4)", "PI (08/10/18)", "RUN SPD",
            "ARM POW", "UNK8", "Const14"
        ])

        # Pitching tab
        self.pitch_table = QTableWidget(3, 8)
        self.pitch_table.setHorizontalHeaderLabels([
            "Profile #", "Hand", "Delivery", "Stamina", "Quality", "Tune", "Skill(0-4)", "Mult"
        ])

        # Team Colors tab
        self.colors_tab = QWidget()
        colors_layout = QVBoxLayout(self.colors_tab)
        title = QLabel("Team Colors (NES palette indices)")
        colors_layout.addWidget(title)
        row1 = QHBoxLayout(); row2 = QHBoxLayout()
        # Primary
        row1.addWidget(QLabel("Primary:"))
        self.primary_combo = QComboBox()
        for idx in sorted(LLB_COLOR_PALETTE_MAP.keys()):
            self.primary_combo.addItem(f"0x{idx:02X}", idx)
        self.primary_swatch = make_swatch(QColor(0,0,0))
        row1.addWidget(self.primary_combo); row1.addWidget(self.primary_swatch)
        # Secondary
        row2.addWidget(QLabel("Secondary:"))
        self.secondary_combo = QComboBox()
        for idx in sorted(LLB_COLOR_PALETTE_MAP.keys()):
            self.secondary_combo.addItem(f"0x{idx:02X}", idx)
        self.secondary_swatch = make_swatch(QColor(0,0,0))
        row2.addWidget(self.secondary_combo); row2.addWidget(self.secondary_swatch)
        colors_layout.addLayout(row1)
        colors_layout.addLayout(row2)
        # Save colors button
        row3 = QHBoxLayout(); row3.addStretch(1)
        save_colors = QPushButton("Save Team Colors"); save_colors.clicked.connect(self.on_save_colors)
        row3.addWidget(save_colors)
        colors_layout.addLayout(row3)
        # Swatch updates
        self.primary_combo.currentIndexChanged.connect(self.on_palette_changed)
        self.secondary_combo.currentIndexChanged.connect(self.on_palette_changed)

        self.tabs.addTab(self.roster_table, "Roster")
        self.tabs.addTab(self.pitch_table, "Pitching")
        self.tabs.addTab(self.colors_tab, "Team Colors")
        root.addWidget(self.tabs)

        bottom = QHBoxLayout()
        save = QPushButton("Save ROM"); save.clicked.connect(self.on_save)
        save_ips = QPushButton("Save IPS Patch"); save_ips.clicked.connect(self.on_save_ips)
        bottom.addWidget(save); bottom.addWidget(save_ips)
        root.addLayout(bottom)

    # --- File / loading ---
    def on_browse(self):
        path,_ = QFileDialog.getOpenFileName(self,"Open ROM",os.getcwd(),"NES ROM (*.nes)")
        if path:
            self.rom_edit.setText(path)
            self.team_combo.setEnabled(True)

    def on_load_selected_team(self):
        rom = self.rom_edit.text().strip()
        if not os.path.isfile(rom):
            QMessageBox.warning(self, "Load", "Choose a valid ROM file.")
            return
        team = self.team_combo.currentText()
        start = TEAM_OFFSETS.get(team)
        if start is None:
            QMessageBox.information(self, "Offset needed",
                                    f"Offset for '{team}' is not set yet.")
            return
        try:
            self.model = RosterModel(rom, start)
            self.loaded_team = team
        except Exception as e:
            QMessageBox.critical(self, "Load", str(e))
            return
        self.populate_roster()
        self.populate_pitching()
        self.populate_colors()

    # --- Populate tabs ---
    def populate_roster(self):
        self.roster_table.setRowCount(len(self.model.players))
        for r,p in enumerate(self.model.players):
            self.roster_table.setItem(r,0,QTableWidgetItem(p.name))
            # Byte6 => hand/size (bat side mirrors hand)
            is_left = bool(p.body_type & 0x80)
            size = SIZE_FROM_CODE.get(p.body_type & 0x03, "Tall")
            bat_c  = QComboBox(); bat_c.addItems(["Right","Left"]) ; bat_c.setCurrentText("Left" if is_left else "Right")
            size_c = QComboBox(); size_c.addItems(["Tall","Fat","Short"]) ; size_c.setCurrentText(size)
            self.roster_table.setCellWidget(r,1,bat_c)
            self.roster_table.setCellWidget(r,2,size_c)
            # Byte11 HIT (0–4)
            hit = QSpinBox(); hit.setRange(0,4); hit.setValue(p.hit)
            self.roster_table.setCellWidget(r,3,hit)
            # Byte12 PI
            pi = QComboBox(); [pi.addItem(f"0x{v:02X}", v) for v in PI_CHOICES]
            pi.setCurrentIndex(max(0, PI_CHOICES.index(p.pi) if p.pi in PI_CHOICES else 0))
            self.roster_table.setCellWidget(r,4,pi)
            # Byte10 SPEED
            spd = QSpinBox(); spd.setRange(0,255); spd.setValue(p.speed)
            self.roster_table.setCellWidget(r,5,spd)
            # Byte9 ARM
            arm = QSpinBox(); arm.setRange(0,255); arm.setValue(p.arm)
            self.roster_table.setCellWidget(r,6,arm)
            # Byte8 UNK8
            unk8 = QSpinBox(); unk8.setRange(0,255); unk8.setValue(p.unk8)
            self.roster_table.setCellWidget(r,7,unk8)
            # Byte14 Const14
            c14 = QComboBox(); [c14.addItem(f"0x{v:02X}", v) for v in CONST14_CHOICES]
            if p.const14 not in CONST14_CHOICES:
                c14.insertItem(0, f"0x{p.const14:02X}", p.const14); c14.setCurrentIndex(0)
            else:
                c14.setCurrentIndex(CONST14_CHOICES.index(p.const14))
            self.roster_table.setCellWidget(r,8,c14)

    def populate_pitching(self):
        self.pitch_table.setRowCount(len(self.model.profiles) if self.model.profiles else 3)
        for i, pr in enumerate(self.model.profiles):
            self.pitch_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            hand = QComboBox(); hand.addItems(["Right","Left"]) ; hand.setCurrentText(pr.hand)
            self.pitch_table.setCellWidget(i,1,hand)
            delv = QComboBox(); delv.addItems(["Normal","Hard","Sidearm"]) ; delv.setCurrentText(pr.delivery)
            self.pitch_table.setCellWidget(i,2,delv)
            st  = QSpinBox(); st.setRange(0,255); st.setValue(pr.stamina)
            ql  = QSpinBox(); ql.setRange(0,255); ql.setValue(pr.quality)
            tn  = QSpinBox(); tn.setRange(0,15);  tn.setValue(pr.tune)
            sk  = QSpinBox(); sk.setRange(0,4);   sk.setValue(pr.skill)
            mu  = QComboBox(); [mu.addItem(f"0x{v:02X}", v) for v in [0x00,0x02]] ; mu.setCurrentIndex(0 if pr.mult==0 else 1)
            self.pitch_table.setCellWidget(i,3,st)
            self.pitch_table.setCellWidget(i,4,ql)
            self.pitch_table.setCellWidget(i,5,tn)
            self.pitch_table.setCellWidget(i,6,sk)
            self.pitch_table.setCellWidget(i,7,mu)

    def populate_colors(self):
        if not self.loaded_team:
            return
        current = self.model.read_team_colors(self.loaded_team)
        if current:
            prim, sec = current
            i1 = self.primary_combo.findData(prim)
            if i1 != -1:
                self.primary_combo.setCurrentIndex(i1)
            i2 = self.secondary_combo.findData(sec)
            if i2 != -1:
                self.secondary_combo.setCurrentIndex(i2)
        # ensure swatches reflect current selection and buffer is updated
        self.on_palette_changed()

    # --- Harvest & Save ---
    def harvest_players(self) -> List[Player]:
        out: List[Player] = []
        for r,p in enumerate(self.model.players):
            name = self.roster_table.item(r,0).text() if self.roster_table.item(r,0) else p.name
            bat  = self.roster_table.cellWidget(r,1).currentText()  # type: ignore
            size = self.roster_table.cellWidget(r,2).currentText()  # type: ignore
            hit  = self.roster_table.cellWidget(r,3).value()        # type: ignore
            piw  = self.roster_table.cellWidget(r,4)                # type: ignore
            pi   = piw.currentData() if hasattr(piw,'currentData') else p.pi
            spd  = self.roster_table.cellWidget(r,5).value()        # type: ignore
            arm  = self.roster_table.cellWidget(r,6).value()        # type: ignore
            unk8 = self.roster_table.cellWidget(r,7).value()        # type: ignore
            c14w = self.roster_table.cellWidget(r,8)                # type: ignore
            const14 = c14w.currentData() if hasattr(c14w,'currentData') else p.const14
            # Byte6 couples hand & bat side; derive from bat side + size
            body_code = CODE_FROM_SIZE.get(size,0)
            if bat == "Left":
                body_code |= 0x80
            out.append(Player(name, body_code, unk8, arm, spd, hit, pi, const14, p.row_offset))
        return out

    def harvest_profiles(self) -> List[PitchProfile]:
        out: List[PitchProfile] = []
        for i, pr in enumerate(self.model.profiles):
            hand = self.pitch_table.cellWidget(i,1).currentText()   # type: ignore
            delv = self.pitch_table.cellWidget(i,2).currentText()   # type: ignore
            st   = self.pitch_table.cellWidget(i,3).value()         # type: ignore
            ql   = self.pitch_table.cellWidget(i,4).value()         # type: ignore
            tn   = self.pitch_table.cellWidget(i,5).value()         # type: ignore
            sk   = self.pitch_table.cellWidget(i,6).value()         # type: ignore
            muw  = self.pitch_table.cellWidget(i,7)                 # type: ignore
            mu   = muw.currentData() if hasattr(muw,'currentData') else pr.mult
            new = PitchProfile(pr.offset, bytearray(pr.raw))
            new.hand = hand
            new.delivery = delv
            new.stamina = st
            new.quality = ql
            new.tune    = tn
            new.skill   = sk
            new.mult    = mu
            out.append(new)
        return out

    def on_save(self):
        if not self.model:
            QMessageBox.information(self, "Save", "Load a team first.")
            return
        # Harvest roster & profiles
        players = self.harvest_players()
        profiles = self.harvest_profiles()
        self.model.apply_players(players)
        self.model.apply_profiles(profiles)
        # Also capture CURRENT Team Colors directly, so no extra click is needed
        if self.loaded_team is not None:
            try:
                prim_idx = self.primary_combo.currentData()
                sec_idx  = self.secondary_combo.currentData()
                if prim_idx is not None and sec_idx is not None:
                    self.model.write_team_colors(self.loaded_team, prim_idx, sec_idx)
            except Exception:
                pass
        path,_=QFileDialog.getSaveFileName(self,"Save",os.getcwd(),"NES ROM (*.nes)")
        if path: self.model.save_rom(path)

    def on_save_ips(self):
        if not self.model:
            QMessageBox.information(self, "Patch", "Load a team first.")
            return
        with open(self.model.rom_path, 'rb') as f:
            orig = f.read()
        # Make sure we apply current UI state for everything, including Team Colors
        players = self.harvest_players()
        profiles = self.harvest_profiles()
        self.model.apply_players(players)
        self.model.apply_profiles(profiles)
        if self.loaded_team is not None:
            try:
                prim_idx = self.primary_combo.currentData()
                sec_idx  = self.secondary_combo.currentData()
                if prim_idx is not None and sec_idx is not None:
                    self.model.write_team_colors(self.loaded_team, prim_idx, sec_idx)
            except Exception:
                pass
        ips = self._build_ips(orig, bytes(self.model.buf))
        path,_=QFileDialog.getSaveFileName(self,"Save IPS Patch",os.getcwd(),"IPS Patch (*.ips)")
        if path:
            with open(path,'wb') as f: f.write(ips)

    def on_save_colors(self):
        if not (self.model and self.loaded_team):
            QMessageBox.information(self, "Colors", "Load a team first.")
            return
        prim_idx = self.primary_combo.currentData()
        sec_idx  = self.secondary_combo.currentData()
        self.model.write_team_colors(self.loaded_team, prim_idx, sec_idx)
        QMessageBox.information(self, "Colors", "Team colors saved to ROM buffer. Use Save ROM/IPS to persist.")

    def update_color_swatches(self):
        # Update both swatches from current combo selections
        p_idx = self.primary_combo.currentData()
        s_idx = self.secondary_combo.currentData()
        p_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(p_idx, "0,0,0"))
        s_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(s_idx, "0,0,0"))
        for frame, col in ((self.primary_swatch,p_col),(self.secondary_swatch,s_col)):
            pal = frame.palette(); pal.setColor(QPalette.Window, col); frame.setPalette(pal)
        # Also auto-apply to ROM buffer if model+team loaded
        if self.model and self.loaded_team:
            try:
                if p_idx is not None and s_idx is not None:
                    self.model.write_team_colors(self.loaded_team, p_idx, s_idx)
            except Exception:
                pass

    @staticmethod
    def on_palette_changed(self, *args, **kwargs):
        # Update swatches and auto-apply palette bytes to the ROM buffer
        try:
            p_idx = self.primary_combo.currentData()
            s_idx = self.secondary_combo.currentData()
        except Exception:
            return
        p_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(p_idx, "0,0,0"))
        s_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(s_idx, "0,0,0"))
        for frame, col in ((self.primary_swatch, p_col), (self.secondary_swatch, s_col)):
            pal = frame.palette(); pal.setColor(QPalette.Window, col); frame.setPalette(pal)
        if self.model and self.loaded_team and p_idx is not None and s_idx is not None:
            self.model.write_team_colors(self.loaded_team, int(p_idx), int(s_idx))
    def on_palette_changed(self, *_):
        # Update swatches and auto-apply palette bytes to the ROM buffer
        try:
            p_idx = self.primary_combo.currentData()
            s_idx = self.secondary_combo.currentData()
        except Exception:
            return
        p_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(p_idx, "0,0,0"))
        s_col = hsv_string_to_qcolor(LLB_COLOR_PALETTE_MAP.get(s_idx, "0,0,0"))
        for frame, col in ((self.primary_swatch, p_col), (self.secondary_swatch, s_col)):
            pal = frame.palette(); pal.setColor(QPalette.Window, col); frame.setPalette(pal)
        if self.model and self.loaded_team and p_idx is not None and s_idx is not None:
            self.model.write_team_colors(self.loaded_team, int(p_idx), int(s_idx))

    def _build_ips(orig: bytes, edited: bytes) -> bytes:
        # Minimal IPS writer
        n = min(len(orig), len(edited))
        o = memoryview(orig)[:n]; e = memoryview(edited)[:n]
        def off3(x:int)->bytes: return bytes([(x>>16)&0xFF,(x>>8)&0xFF,x&0xFF])
        out = bytearray(b"PATCH")
        i=0
        while i<n:
            if o[i]==e[i]:
                i+=1; continue
            start=i
            while i<n and o[i]!=e[i] and (i-start)<65535:
                i+=1
            chunk=e[start:i].tobytes()
            out += off3(start)
            out += bytes([(len(chunk)>>8)&0xFF, len(chunk)&0xFF])
            out += chunk
        out += b"EOF"
        return bytes(out)

if __name__=='__main__':
    app=QApplication([])
    ui=EditorUI(); ui.resize(1200,700); ui.show(); app.exec()
