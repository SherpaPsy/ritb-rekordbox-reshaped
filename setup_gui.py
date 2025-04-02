import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from CTkMessagebox import CTkMessagebox
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'secrets', 'config.json')
ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')
DEFAULT_LOGO = os.path.join(ASSETS_FOLDER, 'default_logo.png')  # Optional logo image
#TODO Add check for existing config file and use that
#TODO Display paths in setup_gui
#TODO When design database add sha for each track and playlist.
#TODO we get to importing from rekordbox - sha each track/playlist and check for existence to make import efficient

class DJSetupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Rekordbox to Access Setup")
        self.geometry("600x500")

        # Logo Image
        if os.path.exists(DEFAULT_LOGO):
            image = ctk.CTkImage(Image.open(DEFAULT_LOGO), size=(150, 150))
            self.logo_label = ctk.CTkLabel(self, image=image, text="")
            self.logo_label.pack(pady=10)

        # DJ Name Entry
        self.dj_name_label = ctk.CTkLabel(self, text="Enter DJ Name:")
        self.dj_name_label.pack()
        self.dj_name_entry = ctk.CTkEntry(self, width=300)
        self.dj_name_entry.pack(pady=5)

        # Rekordbox DB Picker
        self.rekordbox_label = ctk.CTkLabel(self, text="Select Rekordbox DB File:")
        self.rekordbox_label.pack()
        self.rekordbox_button = ctk.CTkButton(self, text="Browse", command=self.browse_rekordbox)
        self.rekordbox_button.pack(pady=5)
        self.rekordbox_path = ""

        # Access DB Location Picker
        self.access_label = ctk.CTkLabel(self, text="Select Folder to Save Access DB:")
        self.access_label.pack()
        self.access_button = ctk.CTkButton(self, text="Browse", command=self.browse_access_folder)
        self.access_button.pack(pady=5)
        self.access_folder = ""

        # Optional Default Cover Image
        self.cover_label = ctk.CTkLabel(self, text="Select Default Cover Image (Optional):")
        self.cover_label.pack()
        self.cover_button = ctk.CTkButton(self, text="Browse", command=self.browse_cover_image)
        self.cover_button.pack(pady=5)
        self.cover_image_path = ""

        # Continue and Exit Buttons
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(pady=20)

        self.continue_button = ctk.CTkButton(self.button_frame, text="Continue", command=self.save_config)
        self.continue_button.grid(row=0, column=0, padx=10)

        self.exit_button = ctk.CTkButton(self.button_frame, text="Exit", command=self.quit)
        self.exit_button.grid(row=0, column=1, padx=10)

    def browse_rekordbox(self):
        path = filedialog.askopenfilename(title="Select Rekordbox DB File", filetypes=[("SQLite DB", "*.db")])
        if path:
            self.rekordbox_path = path

    def browse_access_folder(self):
        folder = filedialog.askdirectory(title="Select Folder for Access DB")
        if folder:
            self.access_folder = folder

    def browse_cover_image(self):
        path = filedialog.askopenfilename(title="Select Cover Image", filetypes=[("Image Files", "*.png;*.jpg;*.jpeg")])
        if path:
            self.cover_image_path = path

    def save_config(self):
        if not self.dj_name_entry.get() or not self.rekordbox_path or not self.access_folder:
            CTkMessagebox(title="Missing Fields", message="Please fill all required fields.")
            return

        formatted_name = self.dj_name_entry.get().lower().replace(' ', '_')
        access_db_path = os.path.join(self.access_folder, f"{formatted_name}.accdb")

        config = {
            "dj_name": self.dj_name_entry.get(),
            "access_db_path": access_db_path,
            "rekordbox_db_path": self.rekordbox_path,
            "default_cover_image": self.cover_image_path
        }

        os.makedirs(os.path.join(os.path.dirname(__file__), 'secrets'), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

        CTkMessagebox(title="Success", message="Configuration saved successfully!")
        self.quit()

if __name__ == "__main__":
    app = DJSetupApp()
    app.mainloop()
