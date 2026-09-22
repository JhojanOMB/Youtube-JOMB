# run.py
import importlib
import customtkinter as ctk
import traceback
import sys

# Obtener CTkFont de forma segura (fallback a tkinter.font.Font)
try:
    CTkFont = ctk.CTkFont
except Exception:
    try:
        from tkinter import font as tkfont
        CTkFont = tkfont.Font
    except Exception:
        CTkFont = None  # si tampoco está, lo dejamos en None

def main():
    try:
        mod = importlib.import_module("gui")
        if hasattr(mod, "main"):
            mod.main()
        elif hasattr(mod, "ttkwindow"):
            mod.ttkwindow.mainloop()
        else:
            raise ImportError("gui no expone ni 'main' ni 'ttkwindow'.")
    except Exception as e:
        print("\n[ERROR] No se pudo iniciar la aplicación.")
        print(f"Excepción: {e}")
        print("Traceback completo:")
        traceback.print_exc(file=sys.stdout)

if __name__ == "__main__":
    main()
