import os
import json
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from CTkMessagebox import CTkMessagebox
from core.config import CONFIG_DIR, CONFIG_FILE, load_config, save_config
from core.rekordbox_reader import auto_detect_rekordbox_db, is_valid_rekordbox_db



class DJSetupApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        print("DJSetupApp __init__ starting")
        self.title("Rekordbox Reshaped Setup")
        self.geometry("600x500")

        self.config = load_config()
        print (f"Loaded config: {self.config}")

        # Check Rekordbox DB path validity
        rek_path = self.config.get("rekordbox_db_path", "")
        print (f"Loaded Rekordbox DB path from config: {rek_path}")
        if not is_valid_rekordbox_db(rek_path):
            print (f"Invalid Rekordbox DB path: {rek_path}")
            print("Attempting auto-detection...")
            auto_path = auto_detect_rekordbox_db()
            print (f"Auto-detected Rekordbox DB path: {auto_path}")
            if auto_path:
                self.config["rekordbox_db_path"] = auto_path
            else:
                self.config["rekordbox_db_path"] = ""

        self.dj_name = self.config.get("dj_name", "")
        self.rekordbox_path = self.config.get("rekordbox_db_path", "")
        self.cover_image_path = self.config.get("default_cover_image", "")

        # Logo
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "default_logo.png")
        if os.path.exists(logo_path):
            image = ctk.CTkImage(Image.open(logo_path), size=(150, 150))
            logo_label = ctk.CTkLabel(self, image=image, text="")
            logo_label.pack(pady=10)

        # DJ Name
        ctk.CTkLabel(self, text="DJ Name:").pack()
        self.dj_name_entry = ctk.CTkEntry(self, width=300)
        self.dj_name_entry.insert(0, self.dj_name)
        self.dj_name_entry.pack(pady=5)

        # Rekordbox DB picker
        ctk.CTkLabel(self, text="Rekordbox DB Path:").pack()
        self.rekordbox_button = ctk.CTkButton(self, text="Browse", command=self.browse_rekordbox)
        self.rekordbox_button.pack(pady=5)

        # Cover Image Picker
        ctk.CTkLabel(self, text="Default Cover Image (optional):").pack()
        self.cover_button = ctk.CTkButton(self, text="Select Image", command=self.browse_cover_image)
        self.cover_button.pack(pady=5)

        # Buttons
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(pady=20)

        ctk.CTkButton(btn_frame, text="Continue", command=self.save_and_exit).grid(row=0, column=0, padx=10)
        ctk.CTkButton(btn_frame, text="Exit", command=self.quit).grid(row=0, column=1, padx=10)

    def browse_rekordbox(self):
        path = filedialog.askopenfilename(title="Select Rekordbox DB", filetypes=[("SQLite DB", "*.db")])
        if path:
            self.rekordbox_path = path

    def browse_cover_image(self):
        path = filedialog.askopenfilename(title="Select Cover Image", filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if path:
            self.cover_image_path = path

    def save_and_exit(self):
        dj_name = self.dj_name_entry.get().strip()
        if not dj_name:
            CTkMessagebox(title="Error", message="DJ name is required.", icon="cancel")
            return
        if not is_valid_rekordbox_db(self.rekordbox_path):
            CTkMessagebox(title="Error", message="Valid Rekordbox DB not selected.", icon="cancel")
            return

        config = {
            "dj_name": dj_name,
            "rekordbox_db_path": self.rekordbox_path,
            "default_cover_image": self.cover_image_path
        }

        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

        CTkMessagebox(title="Success", message="Configuration saved successfully!", icon="check")
        self.quit()


if __name__ == "__main__":
    app = DJSetupApp()
    app.mainloop()
