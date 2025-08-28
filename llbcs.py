#!/usr/bin/env python3
"""
This UI edits a single team block in "Little League Baseball: Championship Series" (NES).

Byte layout after 6-char player name (YOUR VERIFIED MAP):
 6 : Hand/Size (00=R Tall,01=R Fat,02=R Short,80=L Tall,81=L Fat,82=L Short)
 7 : Buffer (always FF)
 8 : Unknown (UNK8)
 9 : ARM Power (defensive throwing)
10 : RUN SPEED
11 : HIT value (UI shows stars = +1, stored 0–4)
12 : PI (pitcher profile selector) → 00 (none), 08 (Profile #1), 10 (Profile #2), 18 (Profile #3)
13 : Buffer
14 : Const14 (team constant/pattern, often 02)
15 : Buffer

Pitcher profiles (3×8 bytes) live AFTER the all-FF padding line that ends the roster rows:
- Layout across two 16-byte rows immediately after the FF line:
  • Profile #1 = bytes 8..15 of first 16-byte row after FF
  • Profile #2 = bytes 0..7  of second 16-byte row after FF
  • Profile #3 = bytes 8..15 of second 16-byte row after FF
- Each profile's byte0: top bit = hand (0x80 left), low nibble = delivery (0=Normal,1=Hard,2=Sidearm)
  byte1=Stamina, byte2=Quality/Movement, byte3=Tune(0–15), byte6=Displayed Pitch skill(0–4), byte7=Mult(00/02)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import os

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QComboBox,
    QMessageBox, QSpinBox, QTabWidget
)

NAME_LEN = 6
ROW_LEN  = 16

# Known team offsets (start of the roster block). Add more as they’re found.
TEAM_OFFSETS = {
    # USA
    "New York":      0x109D0,
    "Illinois":      0x113F0,
    "Texas":         0x10C10,
    "California":    0x10AF0,
    "Florida":       0x11510,
    "Hawaii":        0x10D30,
    "Arizona":       0x10550,
    "Pennsylvania":  0x10670,
    # International
    "Japan":         0x10430,
    "Chinese Taipei":0x10790,
    "Korea":         0x108B0,
    "Mexico":        0x11090,
    "Canada":        0x111B0,
    "Puerto Rico":   0x10F50,
    "Spain":         0x10E50,
    "Italy":         0x112D0,
}


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
CONST14_CHOICES = [0x00, 0x02, 0x03, 0x04]  # keep editable but common values shown

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

    # helpers
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
    def stamina(self) -> int:
        return self.raw[1]
    @stamina.setter
    def stamina(self, v: int):
        self.raw[1] = max(0, min(255, v))

    @property
    def quality(self) -> int:
        return self.raw[2]
    @quality.setter
    def quality(self, v: int):
        self.raw[2] = max(0, min(255, v))

    @property
    def tune(self) -> int:
        return self.raw[3]
    @tune.setter
    def tune(self, v: int):
        self.raw[3] = max(0, min(15, v))

    @property
    def skill(self) -> int:
        return self.raw[6]
    @skill.setter
    def skill(self, v: int):
        self.raw[6] = max(0, min(4, v))

    @property
    def mult(self) -> int:
        return self.raw[7]
    @mult.setter
    def mult(self, v: int):
        self.raw[7] = v & 0xFF

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
        if len(chunk) != ROW_LEN: return None
        name_b = chunk[:NAME_LEN]
        if 0x00 in name_b:
            name_b = name_b.split(b" ", 1)[0]
        name = name_b.decode('ascii','ignore').rstrip(' ')
        attrs = chunk[NAME_LEN:]
        # Respect your verified mapping
        body_type = attrs[0]   # byte6
        # attrs[1] is FF buffer
        unk8      = attrs[2]   # byte8
        arm       = attrs[3]   # byte9
        speed     = attrs[4]   # byte10
        hit       = attrs[5]   # byte11 (0–4)
        pi        = attrs[6]   # byte12
        # attrs[7] is buffer (byte13)
        const14   = attrs[8]   # byte14
        # attrs[9] is buffer (byte15)
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
        # Scan forward by 16 until an all-FF line (team terminator)
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
            # byte13 keep as-is (buffer)
            row[NAME_LEN+8]  = p.const14     # byte14
            # byte15 keep 0x00 (leave existing)
            self.buf[p.row_offset:p.row_offset+ROW_LEN] = row

    def apply_profiles(self, profiles: List[PitchProfile]) -> None:
        self.profiles = profiles
        for pr in profiles:
            self.buf[pr.offset:pr.offset+8] = pr.raw

    def save_rom(self, out_path: str):
        with open(out_path,'wb') as f:
            f.write(self.buf)

class EditorUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLB Roster Editor — Corrected Mapping")
        self.model: Optional[RosterModel] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        # Top bar with team dropdown
        top = QHBoxLayout()
        self.rom_edit = QLineEdit(); self.rom_edit.setPlaceholderText("ROM file")
        browse = QPushButton("Browse"); browse.clicked.connect(self.on_browse)
        self.team_combo = QComboBox()
        ordered_names = [
            "New York","Illinois","Texas","California","Florida","Hawaii","Arizona","Pennsylvania",
            "Japan","Chinese Taipei","Korea","Mexico","Canada","Puerto Rico","Spain","Italy",
            "Custom…",
        ]
        for name in ordered_names:
            self.team_combo.addItem(name)
        self.team_combo.setEnabled(False)
        self.offset_edit = QLineEdit(); self.offset_edit.setPlaceholderText("Custom start offset (e.g. 0x111B0)")
        self.offset_edit.setEnabled(False)
        load = QPushButton("Load Team"); load.clicked.connect(self.on_load_selected_team)
        top.addWidget(QLabel("ROM:")); top.addWidget(self.rom_edit); top.addWidget(browse)
        top.addWidget(QLabel("Team:")); top.addWidget(self.team_combo)
        top.addWidget(self.offset_edit); top.addWidget(load)
        root.addLayout(top)

        # Tabs
        self.tabs = QTabWidget()
        # Roster tab
        self.roster_table = QTableWidget(0, 10)
        self.roster_table.setHorizontalHeaderLabels([
            "Name", "Throw Hand", "Bat Side", "Body Size",
            "HIT (0-4)", "PI (08/10/18)", "RUN SPD (byte10)",
            "ARM POW (byte9)", "UNK8 (byte8)", "Const14 (byte14)"
        ])
        # Pitching tab
        self.pitch_table = QTableWidget(3, 8)
        self.pitch_table.setHorizontalHeaderLabels([
            "Profile #", "Hand", "Delivery", "Stamina", "Quality", "Tune", "Skill(0-4)", "Mult"
        ])
        self.pitch_table.setToolTip(
            "Profiles apply to any player whose PI selects them (00=None, 08/10/18 for #1/#2/#3)."
            "To make a pitcher sidearm: set Delivery=Sidearm on the selected profile (by PI),"
            "and ensure their Byte12 PI points to that profile."
        )

        self.tabs.addTab(self.roster_table, "Roster")
        self.tabs.addTab(self.pitch_table, "Pitching")
        root.addWidget(self.tabs)

        bottom = QHBoxLayout()
        save = QPushButton("Save ROM"); save.clicked.connect(self.on_save)
        save_ips = QPushButton("Save IPS Patch"); save_ips.clicked.connect(self.on_save_ips)
        bottom.addWidget(save); bottom.addWidget(save_ips)
        root.addLayout(bottom)

    def on_browse(self):
        path,_ = QFileDialog.getOpenFileName(self,"Open ROM",os.getcwd(),"NES ROM (*.nes)")
        if path:
            self.rom_edit.setText(path)
            self.team_combo.setEnabled(True)
            # (Re)connect currentIndexChanged safely
            try:
                self.team_combo.currentIndexChanged.disconnect()
            except Exception:
                pass
            self.team_combo.currentIndexChanged.connect(self.on_team_changed)
            self.on_team_changed(self.team_combo.currentIndex())

    def on_team_changed(self, idx: int):
        name = self.team_combo.currentText()
        if name == "Custom…":
            self.offset_edit.setEnabled(True)
        else:
            self.offset_edit.setEnabled(False)

    def on_load_selected_team(self):
        rom = self.rom_edit.text().strip()
        if not os.path.isfile(rom):
            QMessageBox.warning(self, "Load", "Choose a valid ROM file.")
            return
        team = self.team_combo.currentText()
        if team == "Custom…":
            off_txt = self.offset_edit.text().strip()
            try:
                start = int(off_txt, 16)
            except Exception:
                QMessageBox.warning(self, "Load", "Enter a hex offset like 0x111B0 for Custom.")
                return
        else:
            start = TEAM_OFFSETS.get(team)
            if start is None:
                QMessageBox.information(self, "Offset needed",
                    f"Offset for '{team}' is not set yet. Choose 'Custom…' and enter the offset.")
                return
        try:
            self.model = RosterModel(rom, start)
        except Exception as e:
            QMessageBox.critical(self, "Load", str(e))
            return
        self.populate_roster()
        self.populate_pitching()

    # Backward compat
    def on_load(self):
        self.on_load_selected_team()
        rom = self.rom_edit.text().strip()
        if not os.path.isfile(rom):
            QMessageBox.warning(self, "Load", "Choose a valid ROM file.")
            return
        try:
            start = int(self.offset_edit.text(),16)
        except Exception:
            QMessageBox.warning(self,"Err","Bad offset (use hex like 0x111B0)")
            return
        try:
            self.model = RosterModel(rom,start)
        except Exception as e:
            QMessageBox.critical(self,"Load",str(e)); return
        self.populate_roster()
        self.populate_pitching()

    def populate_roster(self):
        self.roster_table.setRowCount(len(self.model.players))
        for r,p in enumerate(self.model.players):
            self.roster_table.setItem(r,0,QTableWidgetItem(p.name))
            # Byte6 => hand/size (bat side mirrors hand in ROM; UI lets you set but we'll sync on save)
            hand = "Left" if (p.body_type & 0x80) else "Right"
            size = SIZE_FROM_CODE.get(p.body_type & 0x03, "Tall")
            hand_c = QComboBox(); hand_c.addItems(["Right","Left"]); hand_c.setCurrentText(hand)
            bat_c  = QComboBox(); bat_c.addItems(["Right","Left"]);  bat_c.setCurrentText(hand)
            size_c = QComboBox(); size_c.addItems(["Tall","Fat","Short"]); size_c.setCurrentText(size)
            self.roster_table.setCellWidget(r,1,hand_c)
            self.roster_table.setCellWidget(r,2,bat_c)
            self.roster_table.setCellWidget(r,3,size_c)
            # Byte11 HIT (0–4)
            hit = QSpinBox(); hit.setRange(0,4); hit.setValue(p.hit)
            self.roster_table.setCellWidget(r,4,hit)
            # Byte12 PI
            pi = QComboBox(); [pi.addItem(f"0x{v:02X}", v) for v in PI_CHOICES]
            pi.setCurrentIndex(max(0, PI_CHOICES.index(p.pi) if p.pi in PI_CHOICES else 0))
            self.roster_table.setCellWidget(r,5,pi)
            # Byte10 SPEED
            spd = QSpinBox(); spd.setRange(0,255); spd.setValue(p.speed)
            self.roster_table.setCellWidget(r,6,spd)
            # Byte9 ARM
            arm = QSpinBox(); arm.setRange(0,255); arm.setValue(p.arm)
            self.roster_table.setCellWidget(r,7,arm)
            # Byte8 UNK8
            unk8 = QSpinBox(); unk8.setRange(0,255); unk8.setValue(p.unk8)
            self.roster_table.setCellWidget(r,8,unk8)
            # Byte14 Const14
            c14 = QComboBox(); [c14.addItem(f"0x{v:02X}", v) for v in CONST14_CHOICES]
            # if current isn't in list, add it so we don't clobber
            if p.const14 not in CONST14_CHOICES:
                c14.insertItem(0, f"0x{p.const14:02X}", p.const14)
                c14.setCurrentIndex(0)
            else:
                c14.setCurrentIndex(CONST14_CHOICES.index(p.const14))
            self.roster_table.setCellWidget(r,9,c14)

    def populate_pitching(self):
        self.pitch_table.setRowCount(len(self.model.profiles) if self.model.profiles else 3)
        for i, pr in enumerate(self.model.profiles):
            self.pitch_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            hand = QComboBox(); hand.addItems(["Right","Left"]); hand.setCurrentText(pr.hand)
            self.pitch_table.setCellWidget(i,1,hand)
            delv = QComboBox(); delv.addItems(["Normal","Hard","Sidearm"]); delv.setCurrentText(pr.delivery)
            self.pitch_table.setCellWidget(i,2,delv)
            st  = QSpinBox(); st.setRange(0,255); st.setValue(pr.stamina)
            ql  = QSpinBox(); ql.setRange(0,255); ql.setValue(pr.quality)
            tn  = QSpinBox(); tn.setRange(0,15);  tn.setValue(pr.tune)
            sk  = QSpinBox(); sk.setRange(0,4);   sk.setValue(pr.skill)
            mu  = QComboBox(); [mu.addItem(f"0x{v:02X}", v) for v in [0x00,0x02]]; mu.setCurrentIndex(0 if pr.mult==0 else 1)
            self.pitch_table.setCellWidget(i,3,st)
            self.pitch_table.setCellWidget(i,4,ql)
            self.pitch_table.setCellWidget(i,5,tn)
            self.pitch_table.setCellWidget(i,6,sk)
            self.pitch_table.setCellWidget(i,7,mu)

    def harvest_players(self) -> List[Player]:
        out: List[Player] = []
        for r,p in enumerate(self.model.players):
            name = self.roster_table.item(r,0).text() if self.roster_table.item(r,0) else p.name
            hand = self.roster_table.cellWidget(r,1).currentText()  # type: ignore
            bat  = self.roster_table.cellWidget(r,2).currentText()  # type: ignore
            size = self.roster_table.cellWidget(r,3).currentText()  # type: ignore
            hit  = self.roster_table.cellWidget(r,4).value()        # type: ignore
            piw  = self.roster_table.cellWidget(r,5)                # type: ignore
            pi   = piw.currentData() if hasattr(piw,'currentData') else p.pi
            spd  = self.roster_table.cellWidget(r,6).value()        # type: ignore
            arm  = self.roster_table.cellWidget(r,7).value()        # type: ignore
            unk8 = self.roster_table.cellWidget(r,8).value()        # type: ignore
            c14w = self.roster_table.cellWidget(r,9)                # type: ignore
            const14 = c14w.currentData() if hasattr(c14w,'currentData') else p.const14
            # Byte6 couples throw/bat hand; enforce match using throw hand
            if bat != hand:
                bat = hand
            body_code = CODE_FROM_SIZE.get(size,0)
            if hand == "Left":
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
        players = self.harvest_players()
        profiles = self.harvest_profiles()
        self.model.apply_players(players)
        self.model.apply_profiles(profiles)
        path,_=QFileDialog.getSaveFileName(self,"Save",os.getcwd(),"NES ROM (*.nes)")
        if path: self.model.save_rom(path)

    def on_save_ips(self):
        if not self.model:
            QMessageBox.information(self, "Patch", "Load a team first.")
            return
        # Build IPS from original vs edited buffer
        with open(self.model.rom_path, 'rb') as f:
            orig = f.read()
        players = self.harvest_players()
        profiles = self.harvest_profiles()
        self.model.apply_players(players)
        self.model.apply_profiles(profiles)
        ips = self._build_ips(orig, bytes(self.model.buf))
        path,_=QFileDialog.getSaveFileName(self,"Save IPS Patch",os.getcwd(),"IPS Patch (*.ips)")
        if path:
            with open(path,'wb') as f: f.write(ips)

    @staticmethod
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
    ui=EditorUI(); ui.resize(1100,650); ui.show(); app.exec()
