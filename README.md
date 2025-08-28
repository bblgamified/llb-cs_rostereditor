# Little League Baseball Roster Editor (NES)

This is a Python/PySide6 application for editing team rosters in **Little League Baseball: Championship Series** on the NES.

## ✨ About
Little League Baseball was one of my favourite games growing up. After spending time with *Baseball Stars* and its player customization, I always wished I could do the same in LLB. Now, decades later, I’ve built a tool to make that possible. I can finally put myself into Williamsport—and more importantly, let my kids experience it through their own eyes.

## 🛠 Features
- Edit player names, handedness, body type, and attributes:
  - **Hit rating (0–4)**
  - **Run speed**
  - **Arm power (defensive throwing)**
  - **Pitching profile (Normal / Hard / Sidearm)**
- Edit pitcher profiles (stamina, movement, tune, skill).
- Save changes directly to a ROM or export an IPS patch for sharing.
- Simple UI with two tabs: **Roster** and **Pitching**.

## Future enhancements
- Team editor to change the name of the team and maybe the colours
- Better understanding of the pitcher profiles for each team
- Add player position editor in a separate tab 

### Likely not going to happen
- Add new teams
- Bigger rosters
- Tournament bracket changes
- Save/load function
- Stats

## 🚀 Usage
1. Install requirements:
   ```bash
   pip install PySide6
2. Run the editor:
   ```bash
   python llbcs.py
3. Load your .nes ROM and the team’s starting offset.
4. Edit roster data and pitcher profiles.
5. Save the modified ROM or create an IPS patch.

## ⚠️ Notes
This editor requires a clean NES ROM of Little League Baseball: Championship Series.

Always back up your ROM before editing.

Offsets must be set manually depending on which team you want to edit.

This project is for educational and nostalgic purposes only.

## 📷 Screenshots
Coming soon

## 📜 License
MIT License – free to use, modify, and share.

## Shout Outs
Big thank you to Davidjoshualightman who did a lot of the heavy lifting and posted his findings to various online sources.
