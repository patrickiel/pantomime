"""A tiny local "Login" app used as a controlled test target.

Stock Tkinter widgets surface to Windows UI Automation as Edit / Button / Text,
so Pantomime can drive it with zero network or external-app dependency.

Run it (in its own window, then bring it to the foreground):

    uv run python examples/login/login_app.py

Valid credentials: demo_user / hunter2. A correct login swaps the form for a
"Welcome, demo_user" message and a "Sign out" button; a wrong one shows a red
"Invalid credentials" message.
"""

from __future__ import annotations

import tkinter as tk

VALID_USER = "demo_user"
VALID_PASS = "hunter2"


class LoginApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Login")
        root.geometry("380x260")

        self.form = tk.Frame(root, padx=24, pady=24)
        self.form.pack(fill="both", expand=True)

        tk.Label(self.form, text="Username").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.user_entry = tk.Entry(self.form, width=28)
        self.user_entry.grid(row=1, column=0, pady=(0, 12))

        tk.Label(self.form, text="Password").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.pass_entry = tk.Entry(self.form, width=28, show="*")
        self.pass_entry.grid(row=3, column=0, pady=(0, 16))

        self.signin = tk.Button(self.form, text="Sign in", width=14, command=self.on_sign_in)
        self.signin.grid(row=4, column=0, sticky="w")

        self.status = tk.Label(self.form, text="", fg="#b00020")
        self.status.grid(row=5, column=0, sticky="w", pady=(12, 0))

        self.welcome: tk.Frame | None = None
        self.user_entry.focus_set()

    def on_sign_in(self) -> None:
        user = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if user == VALID_USER and password == VALID_PASS:
            self.show_welcome(user)
        else:
            self.status.config(text="Invalid credentials")

    def show_welcome(self, user: str) -> None:
        self.form.pack_forget()
        self.welcome = tk.Frame(self.root, padx=24, pady=24)
        self.welcome.pack(fill="both", expand=True)
        tk.Label(self.welcome, text=f"Welcome, {user}", font=("Segoe UI", 14)).pack(pady=(0, 16))
        tk.Label(self.welcome, text="You are logged in.").pack(pady=(0, 16))
        tk.Button(self.welcome, text="Sign out", width=14, command=self.show_form).pack(anchor="w")

    def show_form(self) -> None:
        if self.welcome is not None:
            self.welcome.pack_forget()
            self.welcome = None
        self.pass_entry.delete(0, tk.END)
        self.status.config(text="")
        self.form.pack(fill="both", expand=True)
        self.user_entry.focus_set()


def main() -> None:
    root = tk.Tk()
    LoginApp(root)
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.mainloop()


if __name__ == "__main__":
    main()
