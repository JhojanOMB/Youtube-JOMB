import customtkinter as ctk
root = ctk.CTk()
try:
    b = ctk.CTkButton(root, text="Prueba", corner_radius=10)
    print("CTkButton aceptó corner_radius")
except Exception as e:
    print("Error al crear CTkButton:", repr(e))
finally:
    root.destroy()
